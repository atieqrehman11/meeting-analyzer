"""Stage 2 tools: send_realtime_alert, get_participant_rates, store_cost_snapshot."""
from fastapi import APIRouter, Depends
from shared_models.mcp_types import (
    SendRealtimeAlertInput,
    GetParticipantRatesInput, GetParticipantRatesOutput, ParticipantRate,
    StoreCostSnapshotInput,
)
from app.dependencies import DatabaseDep, GraphDep

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.post("/send_realtime_alert", status_code=204)
async def send_realtime_alert(body: SendRealtimeAlertInput, graph: GraphDep):
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
