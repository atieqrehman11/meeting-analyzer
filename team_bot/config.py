from pydantic_settings import BaseSettings, SettingsConfigDict


class TeamBotSettings(BaseSettings):
    bot_app_id: str = ""
    bot_app_password: str = ""
    bot_base_url: str = "http://localhost:3978"
    mcp_server_url: str = "http://localhost:8000"
    log_level: str = "DEBUG"

    model_config = SettingsConfigDict(env_prefix="BOT_", case_sensitive=False)
