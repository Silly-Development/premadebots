# way to run: python TicketDiscord.py token mode_role_id ticket_creation_channel ticket_transcript_channel

import argparse
import nextcord
import logging
import asyncio
import sys
import os

from nextcord.ext import commands

class AddUser(nextcord.ui.UserSelect):
    def __init__(self, channel):
        super.__init__(
            "Add User To Ticket",
            timeout = None
            )
        self.thread = channel
        
        self.user = nextcord.ui.UserSelect(
            custom_id = "add_user:1",
            placeholder = "Select a user to add to the ticket.",
            max_values = 1
        )
        
        self.add_item(self.user)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        user = self.user
        if user == None:
            return await interaction.send("Please set a user next time | 404 No user found on input")
        overwrite = nextcord.PermissionOverwrite()
        overwrite.read_messages = True
        await self.channel.set_permissions(user, overwrite = overwrite)
        await interaction.send(f"{user.mention} Has been added to the ticket | Success")

class RemoveUser(nextcord.ui.UserSelect):
    def __init__(self, channel):
        super.__init__(
            "Remove User From Ticket",
            timeout = None
            )
        self.thread = channel
        
        self.user = nextcord.ui.UserSelect(
            custom_id = "remove_user:1",
            placeholder = "Select a user to add to the ticket.",
            max_values = 1
        )
        
        self.add_item(self.user)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        user = self.user
        if user == None:
            return await interaction.send("Please set a user next time | 404 No user found on input")
        overwrite = nextcord.PermissionOverwrite()
        overwrite.read_messages = False
        await self.channel.set_permissions(user, overwrite = overwrite)
        await interaction.send(f"{user.mention} Has been removed from the ticket | Success")

class CreateTicket(nextcord.ui.View):
    def __init__(self):
        super.__init__(timeout = None)

        args = self.parse_args()

    @nextcord.ui.button(
        label = "Create A Ticket", style = nextcord.ButtonStyle.blurple, custom_id = "create_ticket:blurple"
    )
    async def CreateTicket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        msg = await interaction.send("A ticket is being created... ", ephemeral = True)

        overwrites = {
            interaction.guild.default_role: nextcord.PermissionOverwrite(read_messages = False),
            interaction.guild.me: nextcord.PermissonOverwrite(read_messages = True),
            interaction.guild.get_role(args.mod_role): nextcord.PermissionOverwrite(read_messages = True)
        }

        channel = args.ticket_creation_channel
        thread = await channel.create_thread(name = f"{interaction.user.name} | Ticket ", overwrites = overwrites)
        
        embed = nextcord.Embed(title = f"Ticket created! | {interaction.user.mention} Created a ticket!", description = "Click on the buttons below to change the ticket's settings!")
        await thread.send(embed = embed, view = TicketSettings())


        await asyncio.sleep(10)
        await msg.edit(f"Success! A ticket has been created! {interaction.channel.mention}")

class TicketSettings(nextcord.ui.View):
    def __init__(self):
        super.__init__(timeout = None)

        args = self.parse_args()

    @nextcord.ui.button(
        label = "Close Ticket", style = nextcord.ButtonStyle.red, custom_id = "ticket_settings:red"
    )
    async def CloseTicket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        messages = await interaction.channel.history(limit = None, oldest_first=True).flatten()
        contents = [message.content for message in messages]
        final = ""
        for msg in contents:
            msg = msg + "\n"
            final = final + msg

        with open('transcript.txt', 'w') as f:
            f.write(final)

        await interaction.response.send_message("The ticket will be closed shortly!")
        await asyncio.sleep(10)
        await self.thread.delete()
        channel = args.ticket_transcript_channel
        await interaction.user.send(f"Your ticket in {interaction.guild_id} was closed succesfully!")
        await channel.send(file=nextcord.File(r"transcript.txt"))
        os.remove("transcript.txt")
    
    @nextcord.ui.button(
        label = "Add Member", style = nextcord.ButtonStyle.green, custom_id = "ticket_settings:green"
    )
    async def AddUserToTicket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_modal(AddUser(interaction.channel))
    
    @nextcord.ui.button(
        label = "Remove Member", style = nextcord.ButtonStyle.gray, custom_id = "ticket_settings:gray"
    )
    async def RemoveUserFromTicket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_modal(RemoveUser(interaction.channel))

class Bot:
    def __init__(self, *args, **kwargs):
        super.__init__(*args, **kwargs)
        self.persisent_views_added = False

    async def on_ready(self):
        if not self.persisent_views_added():
            self.add_view(CreateTicket())
            self.add_view(TicketSettings())
            self.persisent_views_added = True
            print("✅Persistent views added!")
        
        print(f"Bot is up! | Logged in as {self.user}")

class TicketBot:
    def __init__(self, token):
        self.bot = Bot(command_prefix = "!", intents = nextcord.Intents.all())
        self.token = token
    
        @self.bot.slash_command()
        @commands.application_checks.has_permission(manage_guild = True)
        async def setup(interaction: nextcord.Interaction, channel: nextcord.TextChannel):
            await channel.send(embed = nextcord.Embed(type = "rich", title = "Create a ticket", description = "Click the button below to create a ticket and a moderator will be with you shortly!"), view = CreateTicket)

    def run(self):
        self.bot.run(self.token)

def parse_args():
    parser = argparse.ArgumentParser(description="Run a ticket bot on Discord.")
    parser.add_argument('token', type=str, help='Discord Bot Token')
    parser.add_argument("mod_role_id", type = int, help = "Discord Ticket Moderator Role ID")
    parser.add_argument("ticket_creation_channel", type = str, help = "Discord Channel ID to create the ticket threads in")
    parser.add_argument("ticket_transcript_channel", type = str, help = "Discord Channel ID to send the transcrpits at")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup tab.")
        sys.exit(1)
    elif args.mod_role_id == "PUTYOURTICKETMODROLEIDHERE":
        print("You need to set your ticket moderator role id")
        sys.exit(1)
    elif args.ticket_creation_channel == "PUTYOURTICKETCREATIONCHANNELIDHERE":
        print("You need to set your ticket creation channel id")
        sys.exit(1)
    elif args.ticket_creation_channel == "PUTYOURDISCORDTRANSCRIPTCHANNELIDHERE":
        print("You need to set a channel id for ticket trascripts")
        sys.exit(1)

    ticket_bot = TicketBot(args.token)
    ticket_bot.run()
        