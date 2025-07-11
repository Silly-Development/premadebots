"""
Ticketing System
-------------------
Python version: 3.13.5
-------------------
Argument usage: python TicketDiscord.py --token <token> --channel <channel_id> --guild <guild_id> --helper-role-id <role_id>
-------------------
requirements.txt:
nextcord==3.1.0
argparse==1.4.0
-------------------
REQUIREMENTS MAY BE PRESENT IN YOUR PYTHON ENVIRONMENT, CHECK BEFORE CREATING. IF THERE IS NOT A REQUIREMENTS FILE, CREATE ONE AND USE THE CONTENT ABOVE.
PYTHON 3.13.5 MAY BE REQUIRED FOR THE BOT TO WORK, DO NOT CHANGE THE ENVIRONMENT.
-------------------
Made by @techwithnoob
"""


import nextcord
from nextcord.ext import commands
import argparse
import logging
import asyncio

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

open_tickets = {}

class CloseTicketView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="Close Ticket", style=nextcord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await asyncio.sleep(2)
        try:
            del open_tickets[interaction.user.id]
        except KeyError:
            pass
        await interaction.channel.delete()

class TicketPanelView(nextcord.ui.View):
    def __init__(self, bot, channel_id: int, helper_role_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.helper_role_id = helper_role_id

    @nextcord.ui.button(label="Create Ticket", style=nextcord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        user_id = interaction.user.id

        if user_id in open_tickets:
            await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
            return

        guild = interaction.guild
        channel = guild.get_channel(self.channel_id)
        helper_role = guild.get_role(self.helper_role_id)

        thread = await channel.create_thread(
            name=f"ticket-{interaction.user.name}",
            type=nextcord.ChannelType.private_thread,
            invitable=False
        )

        await thread.add_user(interaction.user)

        if helper_role:
            for member in helper_role.members:
                try:
                    await thread.add_user(member)
                except:
                    continue

        open_tickets[user_id] = thread.id

        embed = nextcord.Embed(
            title="Ticket Opened",
            description=f"Hey {interaction.user.mention}, a helper will be with you shortly.",
            color=0x00ff00
        )
        await thread.send(embed=embed, view=CloseTicketView())

        await interaction.response.send_message("✅ Ticket created!", ephemeral=True)

class TicketBot:
    def __init__(self, token, channel_id, guild_id, helper_role_id):
        self.token = token
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.helper_role_id = helper_role_id

        intents = nextcord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        self.bot = commands.Bot(command_prefix='!', intents=intents)

        @self.bot.event
        async def on_ready():
            logger.info(f'{self.bot.user} has connected to Discord!')

        @self.bot.slash_command(name="create_ticket_panel", description="Create a ticket panel", guild_ids=[self.guild_id])
        async def create_ticket_panel(interaction: nextcord.Interaction):
            embed = nextcord.Embed(
                title="🎫 Ticket Panel",
                description="Click the button below to open a ticket.",
                color=0x00ff00
            )
            embed.set_footer(text="Silly Dev - Ticketing System")
            view = TicketPanelView(self.bot, self.channel_id, self.helper_role_id)
            await interaction.response.send_message(embed=embed, view=view)

    def run(self):
        self.bot.run(self.token)

def parse_args():
    parser = argparse.ArgumentParser(description='Discord Bot for Ticketing System')
    parser.add_argument('--token', type=str, required=True, help='Discord Bot Token')
    parser.add_argument('--channel', type=int, required=True, help='Channel ID for ticket threads')
    parser.add_argument('--guild', type=int, required=True, help='Guild ID')
    parser.add_argument('--helper-role-id', type=int, required=True, help='Role ID of helpers')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    ticket_bot = TicketBot(args.token, args.channel, args.guild, args.helper_role_id)
    ticket_bot.run()