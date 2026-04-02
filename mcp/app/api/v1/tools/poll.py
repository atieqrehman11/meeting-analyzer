"""Stage 3 tool: create_poll."""
from fastapi import APIRouter
from shared_models.mcp_types import CreatePollInput, CreatePollOutput
from app.dependencies import GraphDep
from app.common.exceptions import FeatureNotEnabledError
from app.config.settings import settings

router = APIRouter(prefix="/poll", tags=["poll"])


@router.post("/create_poll", response_model=CreatePollOutput)
async def create_poll(body: CreatePollInput, graph: GraphDep):
    if not settings.poll_enabled:
        raise FeatureNotEnabledError("create_poll")
    poll_id = await graph.create_poll(body.meeting_id, body.action_items)
    return CreatePollOutput(poll_id=poll_id)
