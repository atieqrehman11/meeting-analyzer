"""Stage 1 tool: store_transcript_segment."""
from fastapi import APIRouter
from shared_models.mcp_types import StoreTranscriptSegmentInput
from app.dependencies import DatabaseDep
from app.common.exceptions import ConsentRequiredError

router = APIRouter(prefix="/transcript", tags=["transcript"])


@router.post("/store_transcript_segment", status_code=204)
async def store_transcript_segment(body: StoreTranscriptSegmentInput, db: DatabaseDep):
    seg = body.segment
    if not seg.consent_verified:
        raise ConsentRequiredError(seg.participant_id)
    await db.upsert_segment(seg)
