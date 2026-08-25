"""A generic per-player currency ledger (player_currencies). No
gacha/ticket-specific knowledge lives here — see services/tickets.py for
the ticket rules built on top of this, and services/economy.py for Ley
Shards/Echoes, which stay as plain Player columns, not part of this
ledger, for now.

Framework-agnostic — no python-telegram-bot imports (see CLAUDE.md).
None of the functions here call session.commit(): they're building blocks
a caller composes into its own transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ley_shards_bot.models import CurrencyType, PlayerCurrency

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class InsufficientCurrencyError(Exception):
    def __init__(self, currency_type: CurrencyType, required: int, available: int) -> None:
        self.currency_type = currency_type
        self.required = required
        self.available = available
        super().__init__(f"Need {required} {currency_type}, have {available}.")


def _get_or_create_balance(
    session: Session, player_id: int, currency_type: CurrencyType
) -> PlayerCurrency:
    balance = session.get(PlayerCurrency, (player_id, currency_type))
    if balance is None:
        balance = PlayerCurrency(player_id=player_id, currency_type=currency_type, amount=0)
        session.add(balance)
        session.flush()
    return balance


def get_balance(session: Session, player_id: int, currency_type: CurrencyType) -> int:
    return _get_or_create_balance(session, player_id, currency_type).amount


def add(session: Session, player_id: int, currency_type: CurrencyType, amount: int) -> int:
    if amount <= 0:
        msg = "Amount must be positive"
        raise ValueError(msg)
    balance = _get_or_create_balance(session, player_id, currency_type)
    balance.amount += amount
    return balance.amount


def spend(session: Session, player_id: int, currency_type: CurrencyType, amount: int) -> int:
    if amount <= 0:
        msg = "Amount must be positive"
        raise ValueError(msg)
    balance = _get_or_create_balance(session, player_id, currency_type)
    if balance.amount < amount:
        raise InsufficientCurrencyError(currency_type, amount, balance.amount)
    balance.amount -= amount
    return balance.amount
