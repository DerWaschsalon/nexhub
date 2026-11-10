"""Module des Bots, je Bereich ein Ordner (Konzept „TheWashBot – Umbau auf kleine Module“).

MODULES ist die Liste, die der Host lädt; ein neues Modul kommt hier dazu, der Kern bleibt gleich.
"""
from .aion2.runs import RunPosts
from .aion2.schedule import Schedule
from .community.birthdays import Birthdays
from .community.bump import Bump
from .community.giveaways import Giveaways
from .community.levels import Levels
from .community.polls import Polls
from .community.reminders import Reminders
from .community.starboard import Starboard
from .moderation.antispam import Antispam
from .moderation.automod import Automod
from .moderation.cleanup import Cleanup
from .moderation.log import ModerationLog
from .moderation.tickets import Tickets
from .moderation.warnings import Warnings
from .music.player import MusicPlayer
from .notify.feeds import NotificationFeeds
from .server.announcements import Announcements
from .server.counters import Counters
from .server.custom_commands import CustomCommands
from .server.embeds import Embeds
from .server.roles import Roles
from .server.tempvoice import TempVoice
from .server.verification import Verification
from .server.welcome import Welcome
from .system.status import ServerStatus

MODULES = (MusicPlayer, NotificationFeeds, ModerationLog, Antispam, Automod, Warnings, Cleanup, Tickets,
           Welcome, Roles, TempVoice, Counters, Announcements, CustomCommands, Embeds,
           Levels, Starboard, Birthdays, Polls, Reminders, Giveaways, Bump, RunPosts, Schedule,
           ServerStatus, Verification)

__all__ = ["MODULES"]
