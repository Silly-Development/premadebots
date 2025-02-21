import argparse
import discord
import logging
import sys
from discord.ext import commands
from discord import app_commands
from deep_translator import GoogleTranslator

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()

class TranslateBot:
    def __init__(self, token):
        self.token = token
        self.bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

        @self.bot.event
        async def on_ready():
            logger.info(f'Logged in as {self.bot.user}!')
            await self.bot.tree.sync()

        @self.bot.tree.command(name="translate", description="Translate text to a specified language")
        async def translate(interaction: discord.Interaction, text: str, target_lang: str):
            await interaction.response.defer()
            await self.translate_text(interaction, text, target_lang)

    async def translate_text(self, interaction, text, target_lang):
        try:
            translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text)
            await interaction.followup.send(f"**Translated:** {translated_text}")
        except Exception as e:
            await interaction.followup.send("Error in translation. Make sure the target language code is valid.")
            logger.error(f"Translation error: {e}")

    def run(self):
        logger.info("Bot is online and running...")
        self.bot.run(self.token, log_level=logging.ERROR)

def parse_args():
    parser = argparse.ArgumentParser(description="Run a translation bot on Discord.")
    parser.add_argument('token', type=str, help='Discord Bot Token')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup tab.")
        sys.exit(1)

    translate_bot = TranslateBot(args.token)
    translate_bot.run()
