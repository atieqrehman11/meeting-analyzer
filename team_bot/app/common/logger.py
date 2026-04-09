import logging

from team_bot.app.config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

for _noisy in ("httpx", "httpcore", "azure", "urllib3", "msrest", "msal"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("team_bot")
