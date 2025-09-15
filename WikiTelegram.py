import argparse
import telegram
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import wikipediaapi
import requests
import sys
import requests

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()

logging.getLogger("telegram").setLevel(logging.ERROR)

class WikipediaBot:
    def __init__(self, token):
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        self.wikipedia = wikipediaapi.Wikipedia('en', headers={'User-Agent': self.user_agent})
        self.translator = Translator()
        self.application = Application.builder().token(token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT, self.search))

    async def start(self, update, context):
        await update.message.reply_text('Hello! I am a Wikipedia bot. Ask me to search Wikipedia!')

    async def search(self, update, context):
        raw_query = update.message.text
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=telegram.constants.ChatAction.TYPING)
        page = self.wikipedia.page(raw_query)

        if page.exists():
            summary = page.summary[0:5000] 
            translated_summary, _ = self.translator.translate_output(summary, self.get_user_language(update))
            await self.send_long_text(update, translated_summary)
        else:
            await update.message.reply_text("No results found for that search.")

    async def send_long_text(self, update, text):
        chunks = [text[i:i + 3000] for i in range(0, len(text), 3000)]
        for chunk in chunks:
            await update.message.reply_text(chunk)

    def get_user_language(self, update):
        user_language = 'en' 
        if update.message.from_user and update.message.from_user.language_code:
            user_language = update.message.from_user.language_code.lower()
        return user_language

    def run(self):
        logger.info("Bot is online and running...")
        self.application.run_polling()

class Translator:

    def translate_output(self, response, user_lang):
        if user_lang != 'en':
            url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl={user_lang}&q={response}"
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

            try:
                request_result = requests.get(url, headers=headers).json()
                response = request_result[0]
            except Exception as e:
                print(f"Error in translate_output: {e}")
                response = response

        return response, user_lang

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
