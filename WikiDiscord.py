import argparse
import discord
import logging
import wikipediaapi
import sys
from discord.ext import commands
from discord import app_commands
import logging

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger()

class WikipediaBot:
    def __init__(self, token):
        self.token = token
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        self.wikipedia = wikipediaapi.Wikipedia('en', headers={'User-Agent': self.user_agent})
        self.bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

        @self.bot.event
        async def on_ready():
            logger.info(f'Logged in as {self.bot.user}!')
            await self.bot.tree.sync()

        @self.bot.tree.command(name="search", description="Search Wikipedia")
        async def search(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            await self.search(interaction, query)

    async def search(self, interaction, query):
        page = self.wikipedia.page(query)

        if page.exists():
            summary = page.summary[0:5000]
            await self.send_long_text(interaction, summary)
        else:
            await interaction.followup.send("No results found for that search.")

    async def send_long_text(self, interaction, text):
        chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            await interaction.followup.send(chunk)

    def run(self):
        logger.info("Bot is online and running...")
        self.bot.run(self.token,log_level=logging.ERROR)

def parse_args():
    parser = argparse.ArgumentParser(description="Run a Wikipedia bot on Discord.")
    parser.add_argument('token', type=str, help='Discord Bot Token')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup tab.")
        sys.exit(1)

    wiki_bot = WikipediaBot(args.token)
    wiki_bot.run()
