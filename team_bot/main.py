from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from team_bot.app.api.v1.router import router
from team_bot.app.common.logger import logger
from team_bot.app.config.settings import settings
from team_bot.app.api.v1.teams import manager, adapter
from team_bot.graph_service import GraphSubscriptionService

# Module-level reference so the webhook handler can access it without
# circular imports (teams.py imports from main.py lazily at call time).
graph_service: Optional[GraphSubscriptionService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_service

    logger.info("Team bot starting")

    # Start Graph subscription for proactive meeting join if configured
    graph_service = GraphSubscriptionService(
        tenant_id=settings.graph_tenant_id,
        client_id=settings.graph_client_id,
        client_secret=settings.graph_client_secret,
        webhook_url=f"{settings.webhook_base_url.rstrip('/')}/api/graph/webhook",
        webhook_secret=settings.webhook_secret,
        adapter=adapter,
        bot_app_id=settings.bot_app_id,
    )
    await graph_service.subscribe()
    graph_service.start_renewal_loop()

    yield

    await manager.shutdown()
    await graph_service.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)
