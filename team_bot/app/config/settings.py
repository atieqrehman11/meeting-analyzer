from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Meeting Analyzer Teams Bot"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 3978
    reload: bool = False

    bot_app_id: str = ""
    bot_app_password: str = ""
    mcp_server_url: str = "http://localhost:8000"
    mcp_retry_max_attempts: int = 3
    mcp_retry_backoff_seconds: list[int] = [1, 2, 4]
    log_level: str = "INFO"

    model_config = {"env_prefix": "BOT_", "case_sensitive": False}


settings = Settings()
