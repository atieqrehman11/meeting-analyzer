"""Stage 1 tools: get_calendar_event, get_recording_status, store_meeting_record, post_adaptive_card."""
from fastapi import APIRouter
from shared_models.mcp_types import (
    GetCalendarEventInput, CalendarEventOutput,
    GetRecordingStatusInput, GetRecordingStatusOutput,
    StoreMeetingRecordInput, PostAdaptiveCardInput,
)
from app.dependencies import DatabaseDep, GraphDep
from app.common.meeting_id import decode_meeting_id

router = APIRouter(prefix="/meeting", tags=["meeting"])


@router.post("/get_calendar_event", response_model=CalendarEventOutput)
async def get_calendar_event(body: GetCalendarEventInput, graph: GraphDep):
    data = await graph.get_calendar_event(decode_meeting_id(body.meeting_id))
    return CalendarEventOutput(**data)


@router.post("/get_recording_status", response_model=GetRecordingStatusOutput)
async def get_recording_status(body: GetRecordingStatusInput, graph: GraphDep):
    meeting_id = decode_meeting_id(body.meeting_id)
    enabled = await graph.get_recording_status(meeting_id)
    return GetRecordingStatusOutput(meeting_id=meeting_id, recording_enabled=enabled)


@router.post("/store_meeting_record", status_code=204)
async def store_meeting_record(body: StoreMeetingRecordInput, db: DatabaseDep):
    await db.upsert_meeting(body.meeting_record)


@router.post("/post_adaptive_card", status_code=204)
async def post_adaptive_card(body: PostAdaptiveCardInput, graph: GraphDep):
    await graph.post_adaptive_card(decode_meeting_id(body.meeting_id), body.card_payload, body.target_participant_ids)
