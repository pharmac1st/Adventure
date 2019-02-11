from discord.ext import commands
import discord

import inspect
import os
import random
import typing
import time


class Misc:
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def epic(self, ctx):
        await ctx.trigger_typing()
        messages = await ctx.history().filter(
            lambda m: not m.content.startswith("*") and "epic" in m.content.lower() and not m.author.bot
        ).flatten()
        if not messages:
            return await ctx.send("Not epic.")
        await ctx.send(random.choice(messages).jump_url)

    @commands.command(hidden=True)
    async def git(self, ctx):
        async for message in self.bot.get_channel(544405638349062155).history(limit=10).filter(
            lambda m: len(m.embeds) > 0 and m.author.discriminator == "0000"
        ):
            return await ctx.send(embed=message.embeds[0])
        await ctx.send("blank")
        # ideally shouldnt happen

    @commands.command()
    async def avatar(self, ctx, *, member: typing.Union[discord.Member, discord.User] = None):
        member = member or ctx.author
        embed = discord.Embed(color=discord.Colour.blurple())
        embed.set_author(name=str(member), icon_url=member.avatar_url_as(format="png", size=32))
        embed.set_image(url=member.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        start = time.perf_counter()
        await ctx.author.trigger_typing()
        end = time.perf_counter() - start
        await ctx.send(f":ping_pong: **{end*1000:.2f}ms**")

    @commands.command()
    async def source(self, ctx, *, command=None):
        source = "https://github.com/XuaTheGrate/Adventure"
        if not command:
            return await ctx.send(source)

        cmd = self.bot.get_command(command.replace(".", " "))
        if not cmd:
            return await ctx.send("Couldn't find that command.")

        src = cmd.callback
        lines, first = inspect.getsourcelines(src)
        module = inspect.getmodule(src).__name__

        if module.startswith(self.__module__.split(".")[0]):
            location = os.path.relpath(inspect.getfile(src)).replace('\\', '/')
            source += "/blob/master"

        elif module.startswith("jishaku"):
            source = "https://github.com/Gorialis/jishaku/blob/master"
            location = module.replace(".", "/") + ".py"

        else:
            raise RuntimeError("*source")

        final = f"<{source}/{location}#L{first}-L{first + len(lines) - 1}>"
        await ctx.send(final)


def setup(bot):
    bot.add_cog(Misc(bot))
