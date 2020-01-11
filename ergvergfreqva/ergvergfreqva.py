import asyncio
import logging
import os
import random
import dateutil
import discord

from datetime import datetime

import typing
from discord.ext import commands

from core import checks
from core.models import PermissionLevel

logger = logging.getLogger("Modmail")


class YoutubeNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot: discord.Client = bot
        self.db = bot.plugin_db.get_partition(self)
        self.yt_channel = ""
        self.yt_playlist = ""
        self.discord_channel = ""
        self.enabled = True
        self.msg = ""
        self.icon = ""
        self.last_video = ""
        self.api_keys = list()
        self.bot.loop.create_task(self._set_db())

    async def _set_db(self):
        config = await self.db.find_one({"_id": "config"})
        if config is None:
            await self.db.find_one_and_update(
                {"_id": "config"},
                {
                    "$set": {
                        "yt": "",
                        "playlist": "",
                        "lastvideo": "",
                        "icon": "",
                        "message": "",
                        "channel": "",
                        "enabled": True,
                    }
                },
                upsert=True,
            )

        self.yt_channel = config.get("yt", "")
        self.yt_playlist = config.get("playlist", "")
        self.icon = config.get("icon", "")
        self.last_video = config.get("lastvideo", "")
        self.discord_channel = config.get("channel", "")
        self.msg = config.get("message", "")
        self.enabled = config.get("enabled", True)

        self.api_keys = os.getenv("YOUTUBE_KEYS", "").replace(" ", "").split(",")
        if len(self.api_keys) <= 0:
            logger.error("No API key found.")
            self.enabled = False
            return
        self.bot.loop.create_task(self._handle_notify())

    async def _handle_notify(self):
        while True:
            if not self.enabled or (
                self.yt_channel == ""
                or self.discord_channel == ""
                or self.yt_playlist == ""
            ):
                await asyncio.sleep(300)
            else:
                r = await self._check()
                if r["id"]["videoId"] == self.last_video:
                    await asyncio.sleep(300)
                    continue
                else:
                    channel = self.bot.get_channel(int(self.discord_channel)
                    )
                    if channel is None:
                        await asyncio.sleep(300)
                        continue
                    url = f"https://www.youtube.com/watch?v={r['id']['videoId']}"
                    embed = discord.Embed(color=0xC4302B)
                    embed.description = r["snippet"]["description"]
                    embed.set_author(
                        name=r["snippet"]["channelTitle"],
                        url=f"https://youtube.com/channel/f{r['snippet']['channelId']}",
                        icon_url=self.icon
                    )
                    embed.title = r["snippet"]["title"]
                    embed.url = url
                    embed.description = r["snippet"]["description"].split("\n\n")[0]
                    try:
                        embed.set_image(url=f"https://i.ytimg.com/vi/{r['id']['videoId']}/sddefault.jpg")
                    except:
                        pass
                    embed.set_footer(text="Uploaded ")
                    embed.timestamp = dateutil.parser.parse(r["snippet"]["publishedAt"])
                    await channel.send(
                        f"{self.msg.replace('{url}', url) if len(self.msg) > 0 else ' '}",
                        embed=embed,
                    )
                    self.last_video = r["id"]["videoId"]    
                    await self.db.find_one_and_update(
                        {"_id": "config"},
                        {"$set": {"lastvideo": self.last_video}},
                        upsert=True
                        )
                    await asyncio.sleep(300)

    async def _check(self):
        try:
            resp = await self.bot.session.get(
               f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&order=date&safeSearch=none&key={random.choice(self.api_keys)}&channelId={self.yt_channel}",
                headers={"Accept": "application/json"},
            )
            if resp.status == 403:
                if len(self.api_keys) <= 1:
                    log.error("API Ratelimit reached and only one API key provided")
                    return
                return await self._check()
            json = await resp.json()
            return json["items"][0]
        except Exception as e:
            logger.error(e)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def ytnotifier(self, ctx: commands.Context):
        """
        Manage youtube notifier settings
        """

        await ctx.send_help(ctx.command)
        return

    @ytnotifier.command()
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def ytchannel(self, ctx: commands.Context, channelID: str):
        """
        Set the youtube channel ID
        """

        if len(self.api_keys) <= 0:
            logger.error("No API key found.")
            self.enabled = False
            return

        res = await self.bot.session.get(
            f"https://www.googleapis.com/youtube/v3/channels?part=snippet%2CcontentDetails&id={channelID}&key={random.choice(self.api_keys)}",
            headers={"Accept": "application/json"},
        )
        if res.status != 200:
            await ctx.send("Request failed")
            return
        json = await res.json()
        try:
            uploads = json["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            self.yt_playlist = uploads
            self.icon = json["items"][0]["snippet"]["thumbnails"]["default"]["url"]
        # except KeyError:
        #     await ctx.send("Failed. Check the ID Once")
        #     return
        except Exception as e:
            await ctx.send("Failed. Check Logs for more details")
            logger.error(e)
            return

        resp = await self.bot.session.get(
            f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&order=date&safeSearch=none&key={random.choice(self.api_keys)}&channelId={self.yt_channel}",
            headers={"Accept": "application/json"},
        )
        if resp.status != 200:
            await ctx.send("Request failed")
            return
        json1 = await resp.json()
        try:
            last = json1["items"][0]['id']['videoId']
            self.last_video = last
        except Exception as e:
            await ctx.send("Failed. Check Logs for more details")
            logger.error(e)
            return

        await self.db.find_one_and_update(
            {"_id": "config"},
            {
                "$set": {
                    "yt": channelID,
                    "playlist": self.yt_playlist,
                    "lastvideo": self.last_video,
                    "icon": self.icon,
                    "updatedAt": datetime.utcnow(),
                }
            },
            upsert=True,
        )

        self.yt_channel = channelID
        await ctx.send("Done")
        return

    @ytnotifier.command()
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the discord channel to sent the notification to
        """

        await self.db.find_one_and_update(
            {"_id": "config"},
            {"$set": {"channel": str(channel.id), "updatedAt": datetime.utcnow()}},
            upsert=True,
        )

        self.discord_channel = str(channel.id)
        await ctx.send("Done")
        return

    @ytnotifier.command()
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def message(self, ctx: commands.Context, *, msg: str):
        """
        Set a message to be sent with the embed
        """
        await self.db.find_one_and_update(
            {"_id": "config"},
            {"$set": {"message": msg, "updatedAt": datetime.utcnow()}},
            upsert=True,
        )

        self.msg = msg
        await ctx.send("Done")

    @ytnotifier.command()
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def toggle(self, ctx: commands.Context):
        """
        Enable or disable notifications
        """
        await self.db.find_one_and_update(
            {"_id": "config"},
            {"$set": {"enabled": not self.enabled, "updatedAt": datetime.utcnow()}},
            upsert=True,
        )

        self.enabled = not self.enabled
        await ctx.send(f"{'Enabled' if self.enabled else 'Disabled'} the notifications")
        return

    @ytnotifier.command()
    @commands.guild_only()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def test(self, ctx: commands.Context):
        """
        Test the embed.
        """
        r = await self._check()
        url = f"https://www.youtube.com/watch?v={r['id']['videoId']}"
        embed = discord.Embed(color=0xC4302B)
        embed.description = r["snippet"]["description"]
        embed.set_author(
            name=r["snippet"]["channelTitle"],
            url=f"https://youtube.com/channel/f{r['snippet']['channelId']}",
            icon_url=self.icon
        )
        embed.title = r["snippet"]["title"]
        embed.url = url
        try:
            embed.set_image(url=f"https://i.ytimg.com/vi/{r['id']['videoId']}/sddefault.jpg")
        except:
            pass
        embed.description = r["snippet"]["description"].split("\n\n")[0]
        embed.set_footer(text="Uploaded ")
        embed.timestamp = dateutil.parser.parse(r["snippet"]["publishedAt"])
        await ctx.channel.send(
            f"{self.msg.replace('{url}', url) if len(self.msg) > 0 else ' '}",
            embed=embed,
        )

def setup(bot):
    bot.add_cog(YoutubeNotifier(bot))
