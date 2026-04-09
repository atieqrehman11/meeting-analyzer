from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Meeting Assistant Teams Bot"
    app_display_name: str = "Meeting Assistant"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 3978
    reload: bool = False

    app_id: str = ""
    app_password: str = ""
    mcp_server_url: str = "http://localhost:8000"
    mcp_retry_max_attempts: int = 3
    mcp_retry_backoff_seconds: list[int] = [1, 2, 4]
    log_level: str = "DEBUG"

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

    # Bot response messages
    msg_welcome: str = "👋 **{name}** is now active in this meeting. I'll deliver AI-powered insights when the meeting ends. Type **help** to see available commands."
    msg_default: str = "I'm **{name}**. I will help generate post-meeting insights including action items, agenda adherence, and sentiment analysis. Type **help** to get started."
    msg_status: str = "✅ **{name}** is running and ready. Add me to a meeting to begin generating insights."
    msg_help: str = "**{name}** — commands:\n\n• **help** — show this message\n• **status** — check if the bot is running\n\nTo use: add me to a Teams meeting. I'll post a summary with action items when the meeting ends."

    model_config = {"env_prefix": "BOT_", "case_sensitive": False}


settings = Settings()
