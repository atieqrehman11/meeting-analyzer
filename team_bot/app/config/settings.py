from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Meeting Assistant Teams Bot"
    app_display_name: str = "Meeting Assistant"
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

    # Microsoft Graph — required for proactive meeting join via webhook
    # Application permissions needed: OnlineMeetings.Read.All, Calendars.Read
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""

    # Public HTTPS base URL of this bot service (used to register the Graph webhook)
    # e.g. https://<bot-app>.azurecontainerapps.io
    # Leave empty to skip Graph subscription (bot will only join when manually added)
    webhook_base_url: str = ""

    # Secret token sent with every Graph notification — used to validate authenticity
    webhook_secret: str = "change-me-in-production"

    model_config = {"env_prefix": "BOT_", "case_sensitive": False}


settings = Settings()
