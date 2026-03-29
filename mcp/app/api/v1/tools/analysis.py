"""Stage 1 tools: store_analysis_report, get_analysis_report."""
from fastapi import APIRouter
from shared_models.mcp_types import (
    StoreAnalysisReportInput, GetAnalysisReportInput, AnalysisReport,
)
from app.dependencies import DatabaseDep
from app.common.exceptions import McpToolError

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/store_analysis_report", status_code=204)
async def store_analysis_report(body: StoreAnalysisReportInput, db: DatabaseDep):
    await db.upsert_report(body.report)


@router.post("/get_analysis_report", response_model=AnalysisReport)
async def get_analysis_report(body: GetAnalysisReportInput, db: DatabaseDep):
    report = await db.get_report(body.meeting_id)
    if report is None:
        raise McpToolError(
            code="REPORT_NOT_FOUND",
            message=f"No report found for meeting '{body.meeting_id}'.",
            retryable=False,
        )
    return report
