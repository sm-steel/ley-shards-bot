import pytest

from ley_shards_bot.models import BannerType, CurrencyType, Player
from ley_shards_bot.services.currency import get_balance
from ley_shards_bot.services.gacha import PULL_COST_LEY_SHARDS, InsufficientLeyShardsError
from ley_shards_bot.services.players import PlayerRef
from ley_shards_bot.services.tickets import buy_tickets


class TestBuyTickets:
    def test_debits_ley_shards_and_credits_the_matching_ticket_type(self, session):
        session.add(Player(telegram_user_id=1, ley_shards=1000))
        session.commit()

        new_balance = buy_tickets(session, PlayerRef(1), BannerType.STANDARD, 3)

        assert new_balance == 3
        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 3
        player = session.get(Player, 1)
        assert player.ley_shards == 1000 - 3 * PULL_COST_LEY_SHARDS

    def test_event_tickets_credit_the_event_ticket_balance(self, session):
        session.add(Player(telegram_user_id=1, ley_shards=1000))
        session.commit()

        buy_tickets(session, PlayerRef(1), BannerType.EVENT, 2)

        assert get_balance(session, 1, CurrencyType.EVENT_TICKET) == 2
        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 0

    def test_raises_on_insufficient_ley_shards_without_mutating_anything(self, session):
        session.add(Player(telegram_user_id=1, ley_shards=100))
        session.commit()

        with pytest.raises(InsufficientLeyShardsError) as exc_info:
            buy_tickets(session, PlayerRef(1), BannerType.STANDARD, 1)

        assert exc_info.value.required == PULL_COST_LEY_SHARDS
        assert exc_info.value.available == 100
        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 0
        player = session.get(Player, 1)
        assert player.ley_shards == 100

    def test_rejects_a_non_positive_count(self, session):
        session.add(Player(telegram_user_id=1, ley_shards=1000))
        session.commit()

        with pytest.raises(ValueError, match="positive"):
            buy_tickets(session, PlayerRef(1), BannerType.STANDARD, 0)

    def test_captures_username_on_purchase(self, session):
        session.add(Player(telegram_user_id=42, ley_shards=PULL_COST_LEY_SHARDS))
        session.commit()

        new_balance = buy_tickets(session, PlayerRef(42, username="newbie"), BannerType.STANDARD, 1)

        assert new_balance == 1
        player = session.get(Player, 42)
        assert player is not None
        assert player.username == "newbie"

    def test_creates_a_player_row_even_when_insufficient_funds(self, session):
        assert session.get(Player, 99) is None

        with pytest.raises(InsufficientLeyShardsError):
            buy_tickets(session, PlayerRef(99, username="freshface"), BannerType.STANDARD, 1)

        player = session.get(Player, 99)
        assert player is not None
        assert player.username == "freshface"
        assert player.ley_shards == 0
