import argparse
import discord
import logging
import wikipediaapi
import sys
import asyncio
import aiohttp
import time
import hashlib
from collections import defaultdict, OrderedDict
from discord.ext import commands
from discord import app_commands
import logging
import requests

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()

class PerformanceCache:
    def __init__(self, max_size=500, ttl=7200):  # 2 hour TTL for wiki content
        self.cache = OrderedDict()
        self.timestamps = {}
        self.max_size = max_size
        self.ttl = ttl
    
    def _cleanup_expired(self):
        current_time = time.time()
        expired_keys = [key for key, timestamp in self.timestamps.items() 
                       if current_time - timestamp > self.ttl]
        for key in expired_keys:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
    
    def get(self, key):
        self._cleanup_expired()
        if key in self.cache:
            # Move to end (LRU)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None
    
    def set(self, key, value):
        self._cleanup_expired()
        if len(self.cache) >= self.max_size:
            # Remove oldest item
            oldest_key = next(iter(self.cache))
            self.cache.pop(oldest_key)
            self.timestamps.pop(oldest_key)
        
        self.cache[key] = value
        self.timestamps[key] = time.time()

class RateLimiter:
    def __init__(self, max_requests=10, window=60):  # 10 requests per minute
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id):
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests outside the window
        self.requests[user_id] = [req_time for req_time in user_requests 
                                 if now - req_time < self.window]
        
        return len(self.requests[user_id]) < self.max_requests
    
    def add_request(self, user_id):
        self.requests[user_id].append(time.time())

class InputValidator:
    @staticmethod
    def validate_query(query):
        if not query or not query.strip():
            return False, "Search query cannot be empty"
        if len(query) > 300:  # Reasonable search limit
            return False, "Search query is too long (maximum 300 characters)"
        # Basic sanitization - remove potentially harmful characters
        query = query.strip()
        if any(char in query for char in ['<', '>', '{', '}', '[', ']']):
            return False, "Search query contains invalid characters"
        return True, query

class WikipediaBot:
    def __init__(self, token):
        self.token = token
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        self.wikipedia = wikipediaapi.Wikipedia('en', headers={'User-Agent': self.user_agent})
        self.bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        self.cache = PerformanceCache(max_size=500, ttl=7200)
        self.rate_limiter = RateLimiter(max_requests=10, window=60)
        self.session = None

        @self.bot.event
        async def on_ready():
            logger.info(f'Logged in as {self.bot.user}!')
            # Create aiohttp session for better performance
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=600)
            )
            await self.bot.tree.sync()
            logger.info("Wikipedia bot is ready and optimized!")

        @self.bot.event
        async def on_close():
            if self.session:
                await self.session.close()

        @self.bot.tree.command(name="search", description="Search Wikipedia")
        async def search(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            await self.search(interaction, query)

    async def search(self, interaction, query):
        user_id = interaction.user.id
        
        # Rate limiting check
        if not self.rate_limiter.is_allowed(user_id):
            await interaction.followup.send(
                "⏳ **Rate limit exceeded!** Please wait a moment before searching again.",
                ephemeral=True
            )
            return
        
        # Input validation
        query_valid, processed_query = InputValidator.validate_query(query)
        if not query_valid:
            await interaction.followup.send(f"❌ **Invalid query:** {processed_query}", ephemeral=True)
            return
        
        query = processed_query
        
        # Create cache key
        cache_key = hashlib.md5(query.lower().encode()).hexdigest()
        
        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for Wikipedia search from user {user_id}")
            await self.send_cached_result(interaction, cached_result, query)
            return
        
        # Add to rate limiter
        self.rate_limiter.add_request(user_id)
        
        try:
            start_time = time.time()
            
            # Run Wikipedia search in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            page = await loop.run_in_executor(None, self.wikipedia.page, query)
            
            if page.exists():
                # Get summary with length limit
                summary = page.summary[:4000] if len(page.summary) > 4000 else page.summary
                
                # Cache the result
                result_data = {
                    'summary': summary,
                    'url': page.fullurl,
                    'title': page.title
                }
                self.cache.set(cache_key, result_data)
                
                processing_time = round((time.time() - start_time) * 1000, 2)
                
                embed = discord.Embed(
                    title=f"📖 {page.title}",
                    description=summary,
                    color=0x0099ff,
                    url=page.fullurl
                )
                embed.set_footer(text=f"⚡ Wikipedia • Processed in {processing_time}ms")
                
                await interaction.followup.send(embed=embed)
                logger.info(f"Wikipedia search completed for user {user_id} in {processing_time}ms")
            else:
                # Try to find similar articles
                search_results = await loop.run_in_executor(
                    None, 
                    lambda: self.wikipedia.search(query, results=3)
                )
                
                if search_results:
                    suggestions = '\n'.join([f"• {result}" for result in search_results[:3]])
                    embed = discord.Embed(
                        title="❓ Article Not Found",
                        description=f"No exact match found for **{query}**\n\n**Did you mean:**\n{suggestions}",
                        color=0xff9900
                    )
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(
                        f"❌ **No results found** for '{query}'. Please try a different search term."
                    )
                    
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏱️ **Search timeout!** The request took too long. Please try again.",
                ephemeral=True
            )
            logger.error(f"Wikipedia search timeout for user {user_id}")
        except Exception as e:
            await interaction.followup.send(
                "❌ **Search error occurred!** Please try again later.",
                ephemeral=True
            )
            logger.error(f"Wikipedia search error for user {user_id}: {e}")
    
    async def send_cached_result(self, interaction, cached_data, query):
        embed = discord.Embed(
            title=f"📖 {cached_data['title']}",
            description=cached_data['summary'],
            color=0x0099ff,
            url=cached_data['url']
        )
        embed.set_footer(text="⚡ Wikipedia • Cached result")
        await interaction.followup.send(embed=embed)

    def run(self):
        logger.info("Wikipedia bot is starting with performance optimizations...")
        try:
            self.bot.run(self.token, log_level=logging.ERROR)
        except Exception as e:
            logger.error(f"Bot failed to start: {e}")
        finally:
            # Cleanup
            if self.session and not self.session.closed:
                asyncio.run(self.session.close())

def parse_args():
    parser = argparse.ArgumentParser(description="Run a Wikipedia bot on Discord.")
    parser.add_argument('token', type=str, help='Discord Bot Token')
    return parser.parse_args()

def check_for_updates():
    version = "1.0.0"
    versionsurl = "https://raw.githubusercontent.com/Silly-Development/premadebots/refs/heads/main/versions.txt"
    bottype = "WikiDiscord.py"
    try:
        response = requests.get(versionsurl)
        if response.status_code == 200:
            versions = response.text.splitlines()
            for line in versions:
                if line.startswith(bottype):
                    latest_version = line.split("==")[1].strip()
                    if latest_version != version:
                        print(f"A new version ({latest_version}) is available. You are using version {version}. We will now update.")
                        updateurl = f"https://raw.githubusercontent.com/Silly-Development/premadebots/refs/heads/main/{bottype}"
                        update_response = requests.get(updateurl)
                        if update_response.status_code == 200:
                            with open(bottype, 'w', encoding='utf-8') as f:
                                f.write(update_response.text)
                            print("Update successful. Please restart the bot to apply changes.")
                        else:
                            print(f"Failed to download the update, status code: {update_response.status_code}")
                    else:
                        print(f"You are using the latest version ({version}).")
                    return
            print("Bot type not found in versions file.")
        else:
            print(f"Failed to check for updates, status code: {response.status_code}")
    except Exception as e:
        print(f"Error checking for updates: {e}")

if __name__ == '__main__':
    args = parse_args()
    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup tab.")
        sys.exit(1)
    check_for_updates()
    wiki_bot = WikipediaBot(args.token)
    wiki_bot.run()
