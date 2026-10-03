import pytest

from ley_shards_bot.config import Config


def _set_all_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "bot-credential-value")
    monkeypatch.setenv("GACHA_TOPIC_ID", "7")
    monkeypatch.setenv("GROUP_CHAT_ID", "-100555")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://appuser:db-pw-value@mariadb:3306/appdb")
    monkeypatch.setenv("TELEGRAM_PROXY_URL", "http://proxyuser:proxy-pw-value@proxyhost:8888")


def test_secret_values_collects_every_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #74: everything the logging filter must mask, by exact value."""
    _set_all_secrets(monkeypatch)

    secrets = Config.from_env().secret_values()

    assert set(secrets) == {"bot-credential-value", "db-pw-value", "proxy-pw-value"}


def test_secret_values_leaves_out_non_secret_parts_of_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_all_secrets(monkeypatch)

    secrets = Config.from_env().secret_values()

    for not_secret in ("appuser", "proxyuser", "mariadb", "proxyhost", "appdb", "-100555"):
        assert not any(not_secret == s for s in secrets)


def test_secret_values_skips_unset_and_empty_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty string in the list would "match" at every position."""
    _set_all_secrets(monkeypatch)
    monkeypatch.delenv("TELEGRAM_PROXY_URL")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://appuser@mariadb:3306/appdb")

    secrets = Config.from_env().secret_values()

    assert secrets == ["bot-credential-value"]
