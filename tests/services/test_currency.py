import pytest

from ley_shards_bot.models import CurrencyType, Player
from ley_shards_bot.services.currency import (
    InsufficientCurrencyError,
    add,
    get_balance,
    spend,
)


class TestGetBalance:
    def test_defaults_to_zero_for_a_player_with_no_row(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()

        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 0


class TestAdd:
    def test_creates_the_row_on_first_add(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()

        new_balance = add(session, 1, CurrencyType.STANDARD_TICKET, 3)

        assert new_balance == 3
        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 3

    def test_accumulates_onto_an_existing_balance(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()
        add(session, 1, CurrencyType.STANDARD_TICKET, 3)

        new_balance = add(session, 1, CurrencyType.STANDARD_TICKET, 2)

        assert new_balance == 5

    def test_currency_types_are_independent(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()
        add(session, 1, CurrencyType.STANDARD_TICKET, 3)

        add(session, 1, CurrencyType.EVENT_TICKET, 7)

        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 3
        assert get_balance(session, 1, CurrencyType.EVENT_TICKET) == 7

    def test_rejects_a_non_positive_amount(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()

        with pytest.raises(ValueError, match="positive"):
            add(session, 1, CurrencyType.STANDARD_TICKET, 0)


class TestSpend:
    def test_debits_a_sufficient_balance(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()
        add(session, 1, CurrencyType.STANDARD_TICKET, 5)

        new_balance = spend(session, 1, CurrencyType.STANDARD_TICKET, 3)

        assert new_balance == 2

    def test_raises_on_insufficient_balance_without_mutating(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()
        add(session, 1, CurrencyType.STANDARD_TICKET, 2)

        with pytest.raises(InsufficientCurrencyError) as exc_info:
            spend(session, 1, CurrencyType.STANDARD_TICKET, 3)

        assert exc_info.value.required == 3
        assert exc_info.value.available == 2
        assert get_balance(session, 1, CurrencyType.STANDARD_TICKET) == 2

    def test_rejects_a_non_positive_amount(self, session):
        session.add(Player(telegram_user_id=1))
        session.commit()

        with pytest.raises(ValueError, match="positive"):
            spend(session, 1, CurrencyType.STANDARD_TICKET, 0)
