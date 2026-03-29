from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from team_bot.app.api.v1.router import router
from team_bot.app.common.logger import logger
from team_bot.app.config.settings import settings
from team_bot.app.api.v1.teams import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Team bot starting")
    yield
    await manager.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)
