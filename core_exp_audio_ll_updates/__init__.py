import asyncio

from redbot import version_info
from redbot.core.bot import Red
from redbot.core.errors import CogLoadError
from redbot.core.utils import get_end_user_data_statement_or_raise

from .cog import CoreExpAudioLavalinkUpdates

__red_end_user_data_statement__ = get_end_user_data_statement_or_raise(__file__)
_COG_ADDED = False


async def setup(bot: Red) -> None:
    if bot.get_cog("Audio") is not None:
        raise CogLoadError(
            "core_exp_audio_ll_updates cog package needs to be loaded BEFORE audio cog package.\n"
            "Fix the cog load order by doing the following:\n"
            "1. Unload audio cog package.\n"
            "2. Load core_exp_audio_ll_updates cog package.\n"
            "3. Load audio cog package.\n\n"
            "The new cog load order will be preserved on future bot starts as well."
        )

    if (version_info.major, version_info.minor, version_info.micro) != (3, 5, 15):
        raise CogLoadError(
            "This experiment can only be ran on Red 3.5.15."
            " Neither older nor newer versions can be used."
        )

    cog = CoreExpAudioLavalinkUpdates(bot)
    await bot.add_cog(cog)
    await cog.initialize()

    global _COG_ADDED
    _COG_ADDED = True


async def teardown(bot: Red) -> None:
    if not _COG_ADDED:
        return

    async def _notify_if_unloaded_by_user():
        await asyncio.sleep(5)
        packages = await bot._config.packages()
        if __name__ not in packages:
            await bot.send_to_owners(
                "The core_exp_audio_ll_updates cog package has been removed from cog packages"
                " that get loaded on startup and its commands are no longer available, however"
                " the effects of the experiment will persist until the bot is restarted."
            )

    asyncio.create_task(_notify_if_unloaded_by_user())
