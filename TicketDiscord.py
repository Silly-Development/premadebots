# way to run: python TicketDiscord.py token mod_role_id ticket_creation_channel ticket_transcript_channel

import argparse
import nextcord
import asyncio
import sys
import os

from nextcord.ext import commands

class AddUser(nextcord.ui.Modal):
    def __init__(self, channel):
        super().__init__(title="Add User To Ticket", timeout=None)
        self.channel = channel
        self.user = nextcord.ui.TextInput(
            label="User ID",
            placeholder="Enter the user ID to add to the ticket",
            required=True
        )
        self.add_item(self.user)

    async def callback(self, interaction: nextcord.Interaction):
        try:
            user_id = int(self.user.value)
            user = await interaction.guild.fetch_member(user_id)
            overwrite = nextcord.PermissionOverwrite()
            overwrite.read_messages = True
            await self.channel.set_permissions(user, overwrite=overwrite)
            await interaction.response.send_message(f"{user.mention} has been added to the ticket!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class RemoveUser(nextcord.ui.Modal):
    def __init__(self, channel):
        super().__init__(title="Remove User From Ticket", timeout=None)
        self.channel = channel
        self.user = nextcord.ui.TextInput(
            label="User ID",
            placeholder="Enter the user ID to remove from the ticket",
            required=True
        )
        self.add_item(self.user)

    async def callback(self, interaction: nextcord.Interaction):
        try:
            user_id = int(self.user.value)
            user = await interaction.guild.fetch_member(user_id)
            overwrite = nextcord.PermissionOverwrite()
            overwrite.read_messages = False
            await self.channel.set_permissions(user, overwrite=overwrite)
            await interaction.response.send_message(f"{user.mention} has been removed from the ticket!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class CreateTicket(nextcord.ui.View):
    def __init__(self, mod_role_id, ticket_creation_channel):
        super().__init__(timeout=None)
        self.mod_role_id = mod_role_id
        self.ticket_creation_channel = ticket_creation_channel

    @nextcord.ui.button(
        label="Create A Ticket", style=nextcord.ButtonStyle.blurple, custom_id="create_ticket"
    )
    async def create_ticket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        msg = await interaction.response.send_message("Creating ticket...", ephemeral=True)

        overwrites = {
            interaction.guild.default_role: nextcord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: nextcord.PermissionOverwrite(read_messages=True),
            interaction.guild.get_role(self.mod_role_id): nextcord.PermissionOverwrite(read_messages=True),
        }

        channel = interaction.guild.get_channel(self.ticket_creation_channel)
        thread = await channel.create_thread(name=f"{interaction.user.name}-ticket", type=nextcord.ChannelType.public_thread)

        embed = nextcord.Embed(title="Ticket Created!", description=f"{interaction.user.mention} created a ticket!")
        await thread.send(embed=embed, view=TicketSettings(thread))

        await asyncio.sleep(2)
        await msg.edit(content=f"Success! Your ticket has been created: {thread.mention}")

class TicketSettings(nextcord.ui.View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @nextcord.ui.button(
        label="Close Ticket", style=nextcord.ButtonStyle.red, custom_id="close_ticket"
    )
    async def close_ticket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        messages = [msg async for msg in self.thread.history(limit=None, oldest_first=True)]
        content = "\n".join([msg.content for msg in messages])

        with open("transcript.txt", "w") as f:
            f.write(content)

        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await asyncio.sleep(2)
        await self.thread.delete()

        transcript_channel = interaction.guild.get_channel(args.ticket_transcript_channel)
        await transcript_channel.send(file=nextcord.File("transcript.txt"))
        os.remove("transcript.txt")

    @nextcord.ui.button(
        label="Add Member", style=nextcord.ButtonStyle.green, custom_id="add_member"
    )
    async def add_user(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_modal(AddUser(self.thread))

    @nextcord.ui.button(
        label="Remove Member", style=nextcord.ButtonStyle.gray, custom_id="remove_member"
    )
    async def remove_user(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_modal(RemoveUser(self.thread))


class TicketBot(commands.Bot):
    def __init__(self, token, mod_role_id, ticket_creation_channel, ticket_transcript_channel):
        intents = nextcord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.token = token
        self.mod_role_id = mod_role_id
        self.ticket_creation_channel = ticket_creation_channel
        self.ticket_transcript_channel = ticket_transcript_channel

    async def on_ready(self):
        self.add_view(CreateTicket(self.mod_role_id, self.ticket_creation_channel))
        print(f"✅ Bot is online as {self.user}")

    @nextcord.slash_command()
    async def setup(self, interaction: nextcord.Interaction, channel: nextcord.TextChannel):
        embed = nextcord.Embed(title="Create a Ticket", description="Click the button below to create a ticket!")
        await channel.send(embed=embed, view=CreateTicket(self.mod_role_id, self.ticket_creation_channel))

    def run_bot(self):
        self.run(self.token)


def parse_args():
    parser = argparse.ArgumentParser(description="Run a ticket bot on Discord.")
    parser.add_argument("token", type=str, help="Discord Bot Token")
    parser.add_argument("mod_role_id", type=int, help="Discord Ticket Moderator Role ID")
    parser.add_argument("ticket_creation_channel", type=int, help="Discord Channel ID to create the ticket threads in")
    parser.add_argument("ticket_transcript_channel", type=int, help="Discord Channel ID to send the transcripts to")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.token == "PUTYOURTOKENHERE":
        print("You need to set the token in the startup.")
        sys.exit(1)
    if args.mod_role_id == "PUTYOURTICKETMODROLEIDHERE":
        print("You need to set your ticket moderator role ID.")
        sys.exit(1)
    if args.ticket_creation_channel == "PUTYOURTICKETCREATIONCHANNELIDHERE":
        print("You need to set your ticket creation channel ID.")
        sys.exit(1)
    if args.ticket_transcript_channel == "PUTYOURDISCORDTRANSCRIPTCHANNELIDHERE":
        print("You need to set your ticket transcript channel ID.")
        sys.exit(1)

    bot = TicketBot(args.token, args.mod_role_id, args.ticket_creation_channel, args.ticket_transcript_channel)
    bot.run_bot()