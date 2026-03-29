from __future__ import annotations

from team_bot.app.config.settings import settings


def test_bot_settings_include_mcp_retry_defaults() -> None:
    assert settings.mcp_retry_max_attempts == 3
    assert settings.mcp_retry_backoff_seconds == [1, 2, 4]
