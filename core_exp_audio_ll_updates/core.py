from redbot.core import commands
from redbot.core.bot import Red


class CoreExpAudioLavalinkUpdates(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
