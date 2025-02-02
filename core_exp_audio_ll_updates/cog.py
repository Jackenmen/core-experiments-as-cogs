import asyncio
import sys

import lavalink
import redbot
from packaging.version import Version
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.views import ConfirmView

from .meta_path_finder import CoreExpAudioLavalinkUpdatesFinder
from .update_manager import ReleaseInfo, ReleaseStream, UpdateManager


async def stop_managed_node(bot: Red) -> None:
    audio_cog = bot.get_cog("Audio")
    if audio_cog is None:
        return
    await lavalink.close(bot)
    audio_cog.lavalink_restart_connect()
    audio_cog.lavalink_connect_task.cancel()
    audio_cog.lavalink_connection_aborted = False
    for node in lavalink.get_all_nodes():
        await node.disconnect()
    if audio_cog.managed_node_controller is not None:
        if not audio_cog.managed_node_controller._shutdown:
            await audio_cog.managed_node_controller.shutdown()
            await asyncio.sleep(5)


def start_managed_node(bot: Red) -> None:
    audio_cog = bot.get_cog("Audio")
    if audio_cog is None:
        return
    audio_cog.lavalink_restart_connect()


class CoreExpAudioLavalinkUpdates(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 2711759130, force_registration=True)
        self.config.register_global(release_info=None)
        self._update_manager: UpdateManager
        self._finder: CoreExpAudioLavalinkUpdatesFinder

    async def cog_load(self) -> None:
        release_info = None
        raw_release_info = await self.config.release_info()
        if raw_release_info is not None:
            release_info = ReleaseInfo.from_json_dict(raw_release_info)

        self._update_manager = UpdateManager(release_info)

    async def initialize(self) -> None:
        self._finder = CoreExpAudioLavalinkUpdatesFinder(self._update_manager)
        sys.meta_path.insert(0, self._finder)

    async def cog_unload(self) -> None:
        sys.meta_path.remove(self._finder)
        await self._update_manager.close()

    @commands.is_owner()
    @commands.group()
    async def llupdates(self, ctx: commands.Context, /) -> None:
        """Commands provided by Lavalink updates experiment for Core Audio cog."""

    @llupdates.group(name="settings")
    async def llupdates_settings(self, ctx: commands.Context, /) -> None:
        """Settings for Lavalink updates."""

    @llupdates.command(name="reset")
    async def llupdates_reset(self, ctx: commands.Context, /) -> None:
        """Reset to default version. Requires bot restart."""
        await self.config.release_info.clear()
        await ctx.send(
            "Lavalink has been reset to default version. To apply the changes, restart the bot."
        )

    @llupdates.command(name="update")
    async def llupdates_update(self, ctx: commands.Context, /) -> None:
        """Update to latest stable Lavalink release compatible with current Red version."""
        await self.update_command(ctx, ReleaseStream.STABLE)

    @llupdates.command(name="previewupdate")
    async def llupdates_previewupdate(self, ctx: commands.Context, /) -> None:
        """Update to latest preview Lavalink release compatible with current Red version."""
        await self.update_command(ctx, ReleaseStream.PREVIEW)

    async def update_command(
        self, ctx: commands.Context, release_stream: ReleaseStream, /
    ) -> None:
        release_index = await self._update_manager.fetch_release_index()
        try:
            latest = release_index.get_latest_release(release_stream)
        except ValueError:
            await ctx.send("The command was unable to find any Lavalink release.")
            return

        try:
            latest_compatible = release_index.get_latest_release(
                release_stream, red_version=Version(redbot.__version__)
            )
        except ValueError:
            await ctx.send(
                "The command was unable to find any Lavalink release compatible with"
                f" your current Red version ({redbot.__version__})."
            )
            return

        # TODO: consider "default" release info
        if self._update_manager.release_info == latest_compatible:
            if latest != latest_compatible:
                await ctx.send(
                    "You are already using latest Lavalink release compatible"
                    f" with your current Red version ({redbot.__version__})."
                    " There is a newer version available for following Red versions:"
                    f" {latest.red_versions}"
                )
            else:
                await ctx.send("You are already using latest Lavalink release.")
            return

        # TODO: validate Java version and at least warn about incompatibility

        view = ConfirmView(ctx.author)
        view.message = await ctx.send(
            "There is a newer Lavalink release available:"
            f" {latest_compatible.release_name} ({latest_compatible.release_stream.name})\n"
            "Do you want to update to this version? This will restart Lavalink"
            " which is going to interrupt all current playing sessions.",
            view=view,
        )

        await view.wait()
        if not view.result:
            await ctx.send("Lavalink will not be updated.")
            return

        old_release_info = self._update_manager.release_info
        self._update_manager.release_info = latest_compatible
        try:
            async with ctx.typing():
                await self.update_node()
        except Exception:
            self._update_manager.release_info = old_release_info
            raise

        await self.config.release_info.set(latest_compatible.as_json_dict())
        await ctx.send("Lavalink has been updated and is now being restarted.")

    async def update_node(self) -> None:
        await stop_managed_node(self.bot)

        from redbot.cogs.audio import manager
        from redbot.cogs.audio.managed_node import ll_server_config
        from redbot.cogs.audio.managed_node import version_pins

        self._update_manager.update_manager(manager)
        self._update_manager.update_ll_server_config(ll_server_config)
        self._update_manager.update_version_pins(version_pins)

        start_managed_node(self.bot)
