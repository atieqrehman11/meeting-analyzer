"""Stage 2 tools: send_realtime_alert, get_participant_rates, store_cost_snapshot."""
from fastapi import APIRouter
from shared_models.mcp_types import (
    SendRealtimeAlertInput,
    GetParticipantRatesInput, GetParticipantRatesOutput, ParticipantRate,
    StoreCostSnapshotInput,
)
from app.dependencies import DatabaseDep, GraphDep
from app.common.exceptions import FeatureNotEnabledError
from app.config.settings import settings

router = APIRouter(prefix="/realtime", tags=["realtime"])

_REALTIME_ALERT_TYPES = {
    "off_track", "agenda_unclear", "agenda_unclear_second",
    "purpose_detected", "purpose_drift",
    "tone_private", "tone_meeting",
    "silent_participant", "missing_agenda",
}


@router.post("/send_realtime_alert", status_code=204)
async def send_realtime_alert(body: SendRealtimeAlertInput, graph: GraphDep):
    if body.alert_type not in _REALTIME_ALERT_TYPES:
        raise FeatureNotEnabledError(f"send_realtime_alert:{body.alert_type}")
    await graph.send_realtime_alert(
        body.meeting_id, body.alert_type, body.card_payload, body.target_participant_ids
    )


@router.post("/get_participant_rates", response_model=GetParticipantRatesOutput)
async def get_participant_rates(body: GetParticipantRatesInput, db: DatabaseDep):
    rates = await db.get_participant_rates(body.participant_ids)
    return GetParticipantRatesOutput(rates=[ParticipantRate(**r) for r in rates])


@router.post("/store_cost_snapshot", status_code=204)
async def store_cost_snapshot(body: StoreCostSnapshotInput, db: DatabaseDep):
    await db.upsert_cost_snapshot(body.snapshot)
