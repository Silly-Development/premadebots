import argparse
import telegram
import logging
import asyncio
import aiohttp
import time
import hashlib
from collections import defaultdict, OrderedDict
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.constants import ChatAction
import wikipediaapi
import requests
import sys

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()
logging.getLogger("telegram").setLevel(logging.ERROR)

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
        # Basic sanitization
        query = query.strip()
        if any(char in query for char in ['<', '>', '{', '}', '[', ']']):
            return False, "Search query contains invalid characters"
        return True, query

class WikipediaBot:
    def __init__(self, token):
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        self.wikipedia = wikipediaapi.Wikipedia('en', headers={'User-Agent': self.user_agent})
        self.translator = Translator()
        self.cache = PerformanceCache(max_size=500, ttl=7200)
        self.rate_limiter = RateLimiter(max_requests=10, window=60)
        self.session = None
        self.application = Application.builder().token(token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT, self.search))

    async def start(self, update, context):
        await update.message.reply_text(
            '📖 **Welcome to Wikipedia Bot!**\n\n'
            '🔍 **Usage:** Send me any search term\n'
            '📄 **Example:** `Python programming` or `Albert Einstein`\n'
            '🌐 **Features:** Auto-translation, fast caching\n'
            '⚡ **Optimized:** Enhanced performance and reliability\n\n'
            'I will search Wikipedia and translate results to your language!'
        )

    async def search(self, update, context):
        user_id = update.effective_user.id
        raw_query = update.message.text
        
        # Skip commands
        if raw_query.startswith('/'):
            return
        
        # Rate limiting check
        if not self.rate_limiter.is_allowed(user_id):
            await update.message.reply_text(
                "⏳ **Rate limit exceeded!** Please wait a moment before searching again."
            )
            return
        
        # Input validation
        query_valid, processed_query = InputValidator.validate_query(raw_query)
        if not query_valid:
            await update.message.reply_text(f"❌ **Invalid query:** {processed_query}")
            return
        
        query = processed_query
        user_lang = self.get_user_language(update)
        
        # Create cache key including user language
        cache_key = hashlib.md5(f"{query.lower()}:{user_lang}".encode()).hexdigest()
        
        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for Wikipedia search from user {user_id}")
            await self.send_cached_result(update, cached_result)
            return
        
        # Add to rate limiter
        self.rate_limiter.add_request(user_id)
        
        # Send typing action for better UX
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action=ChatAction.TYPING
        )
        
        try:
            start_time = time.time()
            
            # Run Wikipedia search in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            page = await loop.run_in_executor(None, self.wikipedia.page, query)
            
            if page.exists():
                # Get summary with length limit
                summary = page.summary[:4000] if len(page.summary) > 4000 else page.summary
                
                # Translate summary to user's language
                translated_summary, _ = await loop.run_in_executor(
                    None, self.translator.translate_output, summary, user_lang
                )
                
                # Cache the result
                result_data = {
                    'summary': translated_summary,
                    'title': page.title,
                    'url': page.fullurl
                }
                self.cache.set(cache_key, result_data)
                
                processing_time = round((time.time() - start_time) * 1000, 2)
                
                await self.send_formatted_result(update, result_data, processing_time)
                logger.info(f"Wikipedia search completed for user {user_id} in {processing_time}ms")
            else:
                # Try to find similar articles
                search_results = await loop.run_in_executor(
                    None, 
                    lambda: self.wikipedia.search(query, results=3)
                )
                
                if search_results:
                    suggestions = '\n'.join([f"• {result}" for result in search_results[:3]])
                    await update.message.reply_text(
                        f"❓ **Article not found**\n\n"
                        f"No exact match for **{query}**\n\n"
                        f"**Did you mean:**\n{suggestions}"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ **No results found** for '{query}'. Please try a different search term."
                    )
                    
        except asyncio.TimeoutError:
            await update.message.reply_text(
                "⏱️ **Search timeout!** The request took too long. Please try again."
            )
            logger.error(f"Wikipedia search timeout for user {user_id}")
        except Exception as e:
            await update.message.reply_text(
                "❌ **Search error occurred!** Please try again later."
            )
            logger.error(f"Wikipedia search error for user {user_id}: {e}")
    
    async def send_formatted_result(self, update, result_data, processing_time):
        chunks = self.smart_chunk_text(result_data['summary'])
        
        # Send first chunk with header
        first_message = (
            f"📖 **{result_data['title']}**\n"
            f"🔗 {result_data['url']}\n\n"
            f"{chunks[0]}"
        )
        
        if processing_time:
            first_message += f"\n\n⚡ *Processed in {processing_time}ms*"
        else:
            first_message += f"\n\n⚡ *Cached result*"
            
        await update.message.reply_text(first_message)
        
        # Send remaining chunks
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)
    
    async def send_cached_result(self, update, cached_data):
        await self.send_formatted_result(update, cached_data, None)
    
    def smart_chunk_text(self, text, max_length=3000):
        """Split text intelligently at sentence boundaries"""
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        sentences = text.split('. ')
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 2 <= max_length:
                current_chunk += sentence + '. '
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + '. '
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text[:max_length]]

    def get_user_language(self, update):
        user_language = 'en' 
        if update.message.from_user and update.message.from_user.language_code:
            user_language = update.message.from_user.language_code.lower()
        return user_language

    def run(self):
        logger.info("Wikipedia bot is starting with performance optimizations...")
        try:
            self.application.run_polling()
        except Exception as e:
            logger.error(f"Bot failed to start: {e}")
        finally:
            # Cleanup if session exists
            if self.session and not self.session.closed:
                asyncio.run(self.session.close())

class Translator:
    def __init__(self):
        self.session = None
    
    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
            )
        return self.session

    def translate_output(self, response, user_lang):
        if user_lang != 'en':
            url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl={user_lang}&q={response}"
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

            try:
                # Use requests for now, but this could be improved with aiohttp in future
                request_result = requests.get(url, headers=headers, timeout=10).json()
                response = request_result[0]
            except Exception as e:
                logger.error(f"Error in translate_output: {e}")
                # Return original response if translation fails
                response = response

        return response, user_lang
    
    def __del__(self):
        if self.session and not self.session.closed:
            try:
                asyncio.run(self.session.close())
            except:
                pass

def parse_args():
    parser = argparse.ArgumentParser(description="Run a Wikipedia bot on Telegram.")
    parser.add_argument('token', type=str, help='Telegram Bot Token')
    return parser.parse_args()

def check_for_updates():
    version = "1.0.0"
    versionsurl = "https://raw.githubusercontent.com/Silly-Development/premadebots/refs/heads/main/versions.txt"
    bottype = "WikiTelegram.py"
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
