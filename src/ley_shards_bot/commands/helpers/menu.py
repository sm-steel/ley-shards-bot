"""Single source of truth for the bot's command menu: which commands
exist, their one-line descriptions, and whether they're admin-only.

Shared by Telegram's `/` autocomplete (app.py's `register_commands`, see
issue #15) and `/help` (`commands/help.py`, see issue #16) so the
two can't drift out of sync with each other.
"""

from __future__ import annotations

from telegram import BotCommand

# Shown to everyone via / autocomplete and always listed in /help.
PLAYER_COMMANDS = [
    BotCommand("daily", "Claim your daily Ley Shards"),
    BotCommand("pull", "Pull once on the gacha banner"),
    BotCommand("pull10", "Pull ten times on the gacha banner"),
    BotCommand("collection", "View your character collection"),
    BotCommand("buy_ticket", "Buy standard/event pull tickets"),
    BotCommand("help", "List available commands"),
]

# Shown only to admins, in addition to PLAYER_COMMANDS above.
ADMIN_COMMANDS = [
    BotCommand("grant", "Grant Ley Shards to a player"),
    BotCommand("revoke", "Deduct Ley Shards from a player"),
    BotCommand("award_guess", "Award a correct-guess bonus"),
]
