"""Stage 3 tool: create_poll."""
from fastapi import APIRouter, Depends
from shared_models.mcp_types import CreatePollInput, CreatePollOutput
from app.dependencies import GraphDep

router = APIRouter(prefix="/poll", tags=["poll"])


@router.post("/create_poll", response_model=CreatePollOutput)
async def create_poll(body: CreatePollInput, graph: GraphDep):
    poll_id = await graph.create_poll(body.meeting_id, body.action_items)
    return CreatePollOutput(poll_id=poll_id)
