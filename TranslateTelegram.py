import argparse
import logging
import sys
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from deep_translator import GoogleTranslator

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()
logging.getLogger("telegram").setLevel(logging.ERROR)

class TranslateBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.translate))

    async def start(self, update, context):
        await update.message.reply_text("Hello! Send me text and a language code (e.g., 'Hello fr') to translate.")

    async def translate(self, update, context):
        text = update.message.text.split()
        if len(text) < 2:
            await update.message.reply_text("Usage: Send a message with text followed by a language code (e.g., 'Hello fr').")
            return
        
        target_lang = text[-1]
        text_to_translate = " ".join(text[:-1])
        
        try:
            translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text_to_translate)
            await update.message.reply_text(f"Translated: {translated_text}")
        except Exception as e:
            await update.message.reply_text("Error in translation. Make sure the target language code is valid.")
            logger.error(f"Translation error: {e}")

    def run(self):
        logger.info("Bot is online and running...")
        self.application.run_polling()

def parse_args():
    parser = argparse.ArgumentParser(description="Run a translation bot on Telegram.")
    parser.add_argument('token', type=str, help='Telegram Bot Token')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    
    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup tab.")
        sys.exit(1)
    
    translate_bot = TranslateBot(args.token)
    translate_bot.run()
