from __future__ import annotations

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from team_bot.app.common.logger import logger
from team_bot.app.config.settings import settings
from team_bot.bot import MeetingOrchestratorManager, TeamsMeetingBot
from team_bot.orchestrator_factory import build_meeting_orchestrator

adapter_settings = BotFrameworkAdapterSettings(
    app_id=settings.bot_app_id,
    app_password=settings.bot_app_password,
)
adapter = BotFrameworkAdapter(adapter_settings)

manager = MeetingOrchestratorManager(build_meeting_orchestrator)
bot = TeamsMeetingBot(manager)

router = APIRouter()


@router.post("/api/messages")
async def messages(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = authorization or ""

    try:
        response = await adapter.process_activity(activity, auth_header, bot.on_turn)
        if response is not None:
            return JSONResponse(content=response.body or {}, status_code=response.status)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content={})
    except Exception as exc:
        logger.exception("Failed to process bot activity")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/api/graph/webhook")
async def graph_webhook(payload: dict) -> dict[str, str]:
    # TODO: implement Graph calendar event subscriptions and proactive join scheduling.
    return {"status": "received"}
