import logging
from app.config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# Suppress noisy third-party loggers
for _noisy in ("httpx", "httpcore", "azure"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("mcp")
