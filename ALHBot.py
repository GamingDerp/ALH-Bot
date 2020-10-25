# Server Index Bot for ALH

from os import path
import json
import asyncio
import time
import re
import traceback
from typing import Optional
import sys
import random

from discord.ext import commands, tasks
import discord
from termcolor import cprint


def get_prefix(bot, msg):
    with open("prefixes.json", "r") as f:
        prefixes = json.load(f)  # type: dict
    guild_id = str(msg.guild.id)
    if guild_id in prefixes:
        return commands.when_mentioned_or(prefixes[guild_id])(bot, msg)
    return commands.when_mentioned_or(bot.config["prefix"])(bot, msg)


class DerpBot(commands.Bot):
    def __init__(self, **options):
        if not path.isfile("config.json"):
            with open("config.json", "w+") as f:
                json.dump({
                    "token": "insert here",
                    "prefix": "!",
                    "server_id": 1234,
                    "category_ids": [1234, 5678],
                    "owner_id": 1234
                }, f, indent=2)
            print("Created a template config.json\nYou can open it as if its a .txt")
            time.sleep(10)
            exit()
        if not path.isfile("prefixes.json"):
            with open("prefixes.json", "w") as f:
                json.dump({}, f)

        self.index = {}
        self.last_updated = None

        super().__init__(command_prefix=get_prefix, **options)

    @property
    def config(self):
        with open("config.json", "r") as f:
            return json.load(f)

    async def on_ready(self):
        cprint("------------------", "green")
        cprint(f"Logged in as\n{bot.user}\n{bot.user.id}", "green")
        cprint(f"{len(bot.guilds)} servers and {len(bot.users)} users", "green")
        cprint("------------------", "green")

        await self.change_presence(activity=discord.Game(name="Sorting through things.."))

        while True:
            try:
                await self.index_servers()
            except:
                print(traceback.format_exc())
            await asyncio.sleep(3600 * 6)  # Update the index every hour

    async def on_command_error(self, context, exception):
        ignored = (commands.CommandNotFound)
        if isinstance(exception, ignored):
            return
        await context.send(embed=discord.Embed(description=str(exception)))
        silent = (
            commands.MissingRequiredArgument,
            commands.CommandOnCooldown,
            commands.BadArgument,
            commands.CheckFailure,
            commands.NotOwner,
            commands.NoPrivateMessage,
            commands.DisabledCommand
        )
        if not isinstance(exception, silent):
            traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)

    async def wait(self, message):
        cprint(message, "yellow", end="\r")
        index = 0
        chars = r"-/-\-"
        while True:
            cprint(f"{message} {chars[index]}", "yellow", end="\r")
            index += 1
            if index + 1 == len(chars):
                index = 0
            await asyncio.sleep(0.21)

    async def index_servers(self):
        status = self.loop.create_task(
            self.wait("Indexing Servers")
        )
        index = {}
        for category_id in self.config["category_ids"]:
            category = self.get_channel(category_id)
            if not category:
                print(f"Couldn't get the category under ID {category_id}")
                continue
            index[category.name.lower()] = {
                channel.name.lower(): {
                    msg.content.split("\n")[0].replace("__**", "").replace("**__", ""): msg.content.split("\n")[1]
                    for msg in list(await channel.history().flatten())
                    if msg.content.count("\n") and msg.content.count("discord.gg")
                }
                for channel in category.text_channels
            }
        self.index = index
        status.cancel()
        print("Successfully Indexed Servers", end="\r")

    async def get_choice(self, ctx, options, user, timeout=30) -> Optional[object]:
        """ Reaction based menu for users to choose between things """

        async def add_reactions(message) -> None:
            for emoji in emojis:
                if not message:
                    return
                try:
                    await message.add_reaction(emoji)
                except discord.errors.NotFound:
                    return
                if len(options) > 5:
                    await asyncio.sleep(1)
                elif len(options) > 2:
                    await asyncio.sleep(0.5)

        def predicate(r, u) -> bool:
            return u.id == user.id and str(r.emoji) in emojis

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️"][:len(options)]
        if not user:
            user = ctx.author

        e = discord.Embed()
        e.set_author(name="Select which option", icon_url=ctx.author.avatar_url)
        e.description = "\n".join(f"{emojis[i]} {option}" for i, option in enumerate(options))
        e.set_footer(text=f"You have 30 seconds")
        message = await ctx.send(embed=e)
        self.loop.create_task(add_reactions(message))

        try:
            reaction, _user = await self.wait_for("reaction_add", check=predicate, timeout=timeout)
        except asyncio.TimeoutError:
            await message.delete()
            return None
        else:
            await message.delete()
            return options[emojis.index(str(reaction.emoji))]

    async def display(self, options: dict, context):
        """ Reaction based configuration """

        async def wait_for_reaction():
            def pred(r, u):
                return u.id == context.author.id and r.message.id == message.id

            try:
                reaction, user = await self.wait_for('reaction_add', check=pred, timeout=60)
            except asyncio.TimeoutError:
                await message.edit(content="Menu Inactive")
                return None
            else:
                return reaction, user

        async def clear_user_reactions(message) -> None:
            message = await context.channel.fetch_message(message.id)
            for reaction in message.reactions:
                if reaction.count > 1:
                    async for user in reaction.users():
                        if user.id == context.author.id:
                            await message.remove_reaction(reaction.emoji, user)
                            break

        async def init_reactions_task() -> None:
            if len(options) > 9:
                other = ["🏡", "◀", "▶"]
                for i, emoji in enumerate(other):
                    if i > 0:
                        await asyncio.sleep(1)
                    await message.add_reaction(emoji)

        pages = []
        tmp_page = {}
        index = 1
        for i, (key, value) in enumerate(options.items()):
            value = options[key]
            if index > 20:
                index = 1
                pages.append(tmp_page)
                tmp_page = {}
                continue
            tmp_page[key] = value
            index += 1
        pages.append(tmp_page)
        page = 0

        def overview():
            e = discord.Embed(color=0x6C3483)
            e.description = ""
            for i, (key, value) in enumerate(pages[page].items()):
                if value:
                    e.description += f"\n• [{key}]({value})"
                else:
                    e.description += f"\n• {key}"
            e.set_footer(text=f"Page {page + 1}/{len(pages)}")
            return e

        message = await context.send(embed=overview())
        self.loop.create_task(init_reactions_task())
        while True:
            await clear_user_reactions(message)
            payload = await wait_for_reaction()
            if not payload:
                return None
            reaction, user = payload
            emoji = str(reaction.emoji)
            if emoji == "🏡":
                await message.edit(embed=overview())
                continue
            elif emoji == "▶":
                page += 1
                await message.edit(embed=overview())
                continue
            elif emoji == "◀":
                page -= 1
                await message.edit(embed=overview())
                continue

    def run(self):
        cprint("Starting bot..", "yellow")
        super().run(self.config["token"])


bot = DerpBot(case_insensitive=True)
bot.remove_command("help")
bot.allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=False)


@bot.command(name="test")
async def test(ctx):
    await ctx.send("I'm up and running")


@bot.command()
async def info(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="ALH Bot Info", icon_url=bot.get_user(bot.config["owner_id"]).avatar_url)
    e.set_thumbnail(url=bot.user.avatar_url)
    e.description = f"Guess I can sort this too.."
    prefix = bot.config["prefix"]
    with open("prefixes.json") as f:
        prefixes = json.load(f)
    if str(ctx.guild.id) in prefixes:
        prefix = prefixes[str(ctx.guild.id)]
    e.add_field(
        name="⍟ Bot Stats ⍟",
        value=f"**Servers:** {len(bot.guilds)}\n"
              f"**Users:** {len(bot.users)}"
    )
    e.add_field(
        name="⍟ Current Index ⍟",
        value=f"**Categories:** {len(bot.index.keys())}"
              f"\n**Servers:** {sum(sum(len(links) for links in section.values()) for section in bot.index.values())}",
        inline=False
    )
    e.add_field(
        name="⍟ Misc ⍟",
        value="**Owner:** GamingDerp#1915"
              f"\n**Bot Dev:** Luck#1574"
              f"\n**Current Prefix:** {prefix}",
        inline=False
    )
    e.add_field(
        name="⍟ Links ⍟",
        value=f"<:AnarchyLinksHub:750895092507869214> [Anarchy Links Hub](https://discord.gg/aGQeKwr)"
              f"\n:gear: [Add ALH-Bot!](https://discord.com/api/oauth2/authorize?client_id=749364874815078523&permissions=387136&scope=bot)"
              f"\n📚 [GitHub](https://github.com/GamingDerp/ALH-Bot)",
        inline=False
    )
    await ctx.send(embed=e)


@bot.command(name="search")
async def search(ctx, *, search_term):
    server = bot.get_guild(bot.config["server_id"])
    search_term = search_term.lower()
    categories = {}
    for channels in bot.index.values():
        for channel, servers in channels.items():
            if search_term in str(channel).lower():
                categories[[c for c in server.text_channels if c.name == channel][0].mention] = None
    if categories:
        choice = await bot.get_choice(ctx, ["Categories", "Discord Names"], ctx.author)
        if choice == "Categories":
            return await bot.display(categories, context=ctx)
    discords = {}
    for channels in bot.index.values():
        for channel, servers in channels.items():
            for server, link in servers.items():
                if search_term in str(server).lower():
                    discords[server] = link
    await bot.display(discords, context=ctx)


@bot.command(name="help")
async def help(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Help", icon_url=bot.get_user(bot.config["owner_id"]).avatar_url)
    e.set_thumbnail(url=bot.user.avatar_url)
    e.description = f"ALH-Bot's Help Menu!"

    e.add_field(
        name="⍟ General ⍟",
        value=f"Help"
              f"\nInfo"
              f"\nNewPrefix"
              f"\nServers"
              f"\nSearch"
              f"\nRandom"
              f"\nTest",
        inline=False
    )
    e.add_field(
        name="⍟ Fun ⍟",
        value=f"\nCoinflip"
              f"\n8ball"
              f"\nGay"
              f"\nPhrase"
              f"\nCute"
              f"\n⠀"
              f"\n More coming soon! :wink:",
    inline = False
    )
    await ctx.send(embed=e)


@bot.command(name="random")
async def random_server(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Random Server", icon_url=ctx.author.avatar_url)
    selection = []
    for channels in bot.index.values():
        for channel, index in channels.items():
            for server, link in index.items():
                selection.append([server, link])
    choice = random.choice(selection)
    e.description = f"[{choice[0]}]({choice[1]})"
    await ctx.send(embed=e)


@bot.command(name="newprefix")
@commands.has_permissions(manage_messages=True)
async def newprefix(ctx, *, new_prefix):
    guild_id = str(ctx.guild.id)
    with open("prefixes.json", "r") as f:
        prefixes = json.load(f)  # type: dict
    if new_prefix == bot.config["prefix"]:
        if guild_id in prefixes:
            del prefixes[guild_id]
        else:
            return await ctx.send("There's no custom prefix being used in this server!")
    else:
        prefixes[guild_id] = new_prefix
        await ctx.send(f"Set the prefix to {new_prefix}")
    with open("prefixes.json", "w") as f:
        json.dump(prefixes, f)


@bot.command(name="Coinflip", aliases=["cf"])
async def coinflip(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Coinflip", icon_url=ctx.author.avatar_url)
    choice = ["Heads", "Tails"]
    e.description = f"{random.choice(choice)}% gay"
    await ctx.send(embed=e)


@bot.command(name="8ball")
async def eight_ball(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="8ball", icon_url=ctx.author.avatar_url)
    choice = ["Yes", "No", "Obviously", "Wtf??", "I'm not sure..", "Maybe...?", "Stop asking.", "Find out for yourself smh", "Crabs"]
    e.description = f"{random.choice(choice)}% gay"
    await ctx.send(embed=e)


@bot.command(name="Gay")
async def gay(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
    e.description = f"{random.randint(0, 100)}% gay"
    await ctx.send(embed=e)


@bot.command(name="Phrase")
async def phrase(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Phrase", icon_url=ctx.author.avatar_url)
    with open("phrases.txt") as f:
        phrases = f.readlines()
        e.description = random.choice(phrases)
    await ctx.send(embed=e)
    
    
@bot.command(name="Cute")
async def cute(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Cute", icon_url=ctx.author.avatar_url)
    with open("cute.txt") as f:
        cute = f.readlines()
    e.set_image(url=random.choice(cute))
    await ctx.send(embed=e)


@bot.command(name="Servers")
async def servers(ctx):
    e = discord.Embed(color=0x6C3483)
    e.set_author(name="Servers", icon_url=ctx.author.avatar_url)
    e.description = f"\n".join(str(guild) for guild in bot.guilds)
    await ctx.send(embed=e)


@bot.event
async def on_message(msg):
    if msg.channel.id == 750140861991354459:
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
    await bot.process_commands(msg)


bot.run()
