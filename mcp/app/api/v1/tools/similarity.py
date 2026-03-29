"""Stage 1 tool: compute_similarity."""
from fastapi import APIRouter
from shared_models.mcp_types import ComputeSimilarityInput, ComputeSimilarityOutput
from app.dependencies import SimilarityDep

router = APIRouter(prefix="/similarity", tags=["similarity"])


@router.post("/compute_similarity", response_model=ComputeSimilarityOutput)
async def compute_similarity(body: ComputeSimilarityInput, svc: SimilarityDep):
    result = svc.compute(body.text, body.agenda_topics, body.meeting_id)
    return ComputeSimilarityOutput(**result)
