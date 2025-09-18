import argparse
import logging
import sys
import asyncio
import aiohttp
import time
import hashlib
from collections import defaultdict, OrderedDict
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from deep_translator import GoogleTranslator
import requests

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()
logging.getLogger("telegram").setLevel(logging.ERROR)

class PerformanceCache:
    def __init__(self, max_size=1000, ttl=3600):  # 1 hour TTL
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
    def __init__(self, max_requests=15, window=60):  # 15 requests per minute
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
    def validate_text(text):
        if not text or not text.strip():
            return False, "Text cannot be empty"
        if len(text) > 4096:  # Telegram message limit
            return False, "Text is too long (maximum 4096 characters)"
        if len(text.encode('utf-8')) > 8000:  # Byte limit for API
            return False, "Text is too large in bytes"
        return True, None
    
    @staticmethod
    def validate_language_code(lang_code):
        if not lang_code or not lang_code.strip():
            return False, "Language code cannot be empty"
        if len(lang_code) > 10:  # Reasonable limit
            return False, "Invalid language code format"
        # Basic sanitization
        lang_code = lang_code.strip().lower()
        if not lang_code.replace('-', '').replace('_', '').isalnum():
            return False, "Language code contains invalid characters"
        return True, lang_code

class TranslateBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.cache = PerformanceCache(max_size=1000, ttl=3600)
        self.rate_limiter = RateLimiter(max_requests=15, window=60)
        self.session = None
        
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.translate))

    async def start(self, update, context):
        await update.message.reply_text(
            "🌐 **Welcome to Translation Bot!**\n\n"
            "📝 **Usage:** Send text followed by language code\n"
            "📄 **Example:** `Hello world fr` (translates to French)\n"
            "⚡ **Features:** Fast caching, rate limiting protection\n"
            "🚀 **Optimized:** Enhanced performance and reliability"
        )

    async def translate(self, update, context):
        user_id = update.effective_user.id
        
        # Rate limiting check
        if not self.rate_limiter.is_allowed(user_id):
            await update.message.reply_text(
                "⏳ **Rate limit exceeded!** Please wait a moment before translating again."
            )
            return
        
        text = update.message.text.split()
        if len(text) < 2:
            await update.message.reply_text(
                "❌ **Invalid format!** \n"
                "📝 **Usage:** Send text followed by language code\n"
                "📄 **Example:** `Hello world fr` (translates to French)"
            )
            return
        
        target_lang = text[-1]
        text_to_translate = " ".join(text[:-1])
        
        # Input validation
        text_valid, text_error = InputValidator.validate_text(text_to_translate)
        if not text_valid:
            await update.message.reply_text(f"❌ **Invalid input:** {text_error}")
            return
        
        lang_valid, processed_lang = InputValidator.validate_language_code(target_lang)
        if not lang_valid:
            await update.message.reply_text(f"❌ **Invalid language code:** {processed_lang}")
            return
        
        target_lang = processed_lang
        
        # Create cache key
        cache_key = hashlib.md5(f"{text_to_translate}:{target_lang}".encode()).hexdigest()
        
        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for translation request from user {user_id}")
            await update.message.reply_text(
                f"🌐 **Translation** ⚡ *Cached*\n\n"
                f"**Original:** {text_to_translate}\n"
                f"**Translated:** {cached_result}\n"
                f"**Language:** {target_lang.upper()}"
            )
            return
        
        # Add to rate limiter
        self.rate_limiter.add_request(user_id)
        
        # Send typing action for better UX
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action=telegram.constants.ChatAction.TYPING
        )
        
        try:
            start_time = time.time()
            
            # Use async timeout for translation
            loop = asyncio.get_event_loop()
            translated_text = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source='auto', target=target_lang).translate(text_to_translate)
            )
            
            if not translated_text:
                raise ValueError("Translation returned empty result")
            
            # Cache the result
            self.cache.set(cache_key, translated_text)
            
            processing_time = round((time.time() - start_time) * 1000, 2)
            
            await update.message.reply_text(
                f"🌐 **Translation** ⚡ *{processing_time}ms*\n\n"
                f"**Original:** {text_to_translate}\n"
                f"**Translated:** {translated_text}\n"
                f"**Language:** {target_lang.upper()}"
            )
            logger.info(f"Translation completed for user {user_id} in {processing_time}ms")
            
        except asyncio.TimeoutError:
            await update.message.reply_text(
                "⏱️ **Translation timeout!** The request took too long. Please try again."
            )
            logger.error(f"Translation timeout for user {user_id}")
        except ValueError as e:
            await update.message.reply_text(
                f"❌ **Translation failed:** {str(e)}\n"
                "Please check your language code and try again."
            )
            logger.error(f"Translation error for user {user_id}: {e}")
        except Exception as e:
            await update.message.reply_text(
                "❌ **Unexpected error occurred!** Please try again later."
            )
            logger.error(f"Unexpected translation error for user {user_id}: {e}")

    def run(self):
        logger.info("Bot is online and running...")
        self.application.run_polling()

def parse_args():
    parser = argparse.ArgumentParser(description="Run a translation bot on Telegram.")
    parser.add_argument('token', type=str, help='Telegram Bot Token')
    return parser.parse_args()

def check_for_updates():
    version = "1.0.0"
    versionsurl = "https://raw.githubusercontent.com/Silly-Development/premadebots/refs/heads/main/versions.txt"
    bottype = "TranslateTelegram.py"
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
    translate_bot = TranslateBot(args.token)
    translate_bot.run()
