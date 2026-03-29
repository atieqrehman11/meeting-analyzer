"""Stage 1 tool: store_consent_record."""
from fastapi import APIRouter
from shared_models.mcp_types import StoreConsentRecordInput
from app.dependencies import DatabaseDep

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/store_consent_record", status_code=204)
async def store_consent_record(body: StoreConsentRecordInput, db: DatabaseDep):
    await db.upsert_consent(body.consent_record)
