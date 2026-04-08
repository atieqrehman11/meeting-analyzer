from __future__ import annotations

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from typing import Annotated, Any
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from team_bot.app.common.logger import logger
from team_bot.app.config.settings import settings
from team_bot.bot import MeetingOrchestratorManager, TeamsMeetingBot
from team_bot.orchestrator_factory import build_meeting_orchestrator

from functools import lru_cache

@lru_cache(maxsize=1)
def _get_adapter() -> BotFrameworkAdapter:
    from botframework.connector.auth import SimpleCredentialProvider
    app_id = settings.app_id.strip()
    app_password = settings.app_password.strip()
    logger.info("Initializing adapter with app_id='%s' (len=%d)", app_id, len(app_id))

    # Override is_valid_appid to add diagnostic logging
    async def _patched_is_valid_appid(self, token_app_id: str) -> bool:
        result = self.app_id == token_app_id
        if not result:
            logger.error(
                "AppId mismatch: token='%s'(len=%d) stored='%s'(len=%d)",
                token_app_id, len(token_app_id),
                self.app_id, len(self.app_id)
            )
        return result
    SimpleCredentialProvider.is_valid_appid = _patched_is_valid_appid

    return BotFrameworkAdapter(BotFrameworkAdapterSettings(
        app_id=app_id,
        app_password=app_password,
    ))

manager = MeetingOrchestratorManager(build_meeting_orchestrator)
bot = TeamsMeetingBot(manager)

router = APIRouter()


class ActivityPayload(BaseModel):
    """
    Teams Bot Framework Activity envelope.
    See: https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-api-reference#activity-object
    """
    type: str
    id: str | None = None
    timestamp: str | None = None
    channelId: str | None = None
    from_: dict[str, Any] | None = None
    recipient: dict[str, Any] | None = None
    conversation: dict[str, Any] | None = None
    text: str | None = None
    membersAdded: list[dict[str, Any]] | None = None
    membersRemoved: list[dict[str, Any]] | None = None
    channelData: dict[str, Any] | None = None
    name: str | None = None
    value: dict[str, Any] | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


@router.post("/api/messages", openapi_extra={"requestBody": {
    "content": {"application/json": {"schema": ActivityPayload.model_json_schema()}},
    "required": True,
}})
async def messages(request: Request, authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = authorization or ""

    logger.debug("Incoming activity: body=%s auth_header=%s", body, auth_header)
    try:
        response = await _get_adapter().process_activity(activity, auth_header, bot.on_turn)
        
        if response is not None:
            return JSONResponse(content=response.body or {}, status_code=response.status)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content={})
    except Exception as exc:
        logger.exception("Failed to process bot activity")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/api/graph/webhook")
async def graph_webhook_validate(
    validation_token: Annotated[str, Query(alias="validationToken")],
) -> PlainTextResponse:
    """
    Graph subscription validation handshake — GET variant.
    """
    logger.info("Graph webhook GET validation handshake received")
    return PlainTextResponse(content=validation_token, status_code=200)


@router.post("/api/graph/webhook", response_model=None)
async def graph_webhook_notify(
    request: Request,
    validation_token: Annotated[str | None, Query(alias="validationToken")] = None,
) -> PlainTextResponse | JSONResponse:
    """
    Graph change notification handler.
    Graph sends a POST with ?validationToken during subscription creation —
    echo it back as plain text. Real notifications arrive without that param.
    """
    # Validation handshake — Graph POSTs with ?validationToken during subscription setup
    if validation_token:
        logger.info("Graph webhook POST validation handshake received")
        return PlainTextResponse(content=validation_token, status_code=200)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    notifications = body.get("value", [])
    if not notifications:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "accepted"})

    for notification in notifications:
        client_state = notification.get("clientState", "")
        if client_state != settings.webhook_secret:
            logger.warning("Graph notification rejected — clientState mismatch")
            continue

        resource_data = notification.get("resourceData") or {}
        change_type = notification.get("changeType", "")
        meeting_id = resource_data.get("id")

        logger.info("Graph notification: changeType=%s meetingId=%s", change_type, meeting_id)

        if not meeting_id:
            logger.warning("Graph notification missing meeting id — skipping")
            continue

        from team_bot.main import graph_service  # noqa: PLC0415
        if graph_service is not None:
            service_url = notification.get("serviceUrl") or "https://smba.trafficmanager.net/teams/"
            conversation_id = resource_data.get("chatInfo", {}).get("threadId") or meeting_id
            await graph_service.proactive_join(meeting_id, service_url, conversation_id)

    # Graph expects 202 — anything else triggers retries
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "accepted"})
