"""
Domain exceptions and FastAPI exception handlers for the MCP server.
All tool failures surface as McpToolError with a structured error envelope.
"""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class McpToolError(Exception):
    """Raised when a tool call fails. Maps to the MCP error contract."""
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def to_response(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable}}


class FeatureNotEnabledError(McpToolError):
    def __init__(self, tool: str) -> None:
        super().__init__(
            code="FEATURE_NOT_ENABLED",
            message=f"Tool '{tool}' is not active in the current stage.",
            retryable=False,
        )


class ValidationError(McpToolError):
    def __init__(self, message: str) -> None:
        super().__init__(code="VALIDATION_ERROR", message=message, retryable=False)


class ConsentRequiredError(McpToolError):
    def __init__(self, participant_id: str) -> None:
        super().__init__(
            code="CONSENT_REQUIRED",
            message=f"Consent not granted for participant '{participant_id}'.",
            retryable=False,
        )


class RegionViolationError(McpToolError):
    def __init__(self, expected: str, got: str) -> None:
        super().__init__(
            code="REGION_VIOLATION",
            message=f"Cross-region write rejected. Expected '{expected}', got '{got}'.",
            retryable=False,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(McpToolError)
    async def mcp_tool_error_handler(_: Request, exc: McpToolError) -> JSONResponse:
        return JSONResponse(status_code=400, content=exc.to_response())

    @app.exception_handler(Exception)
    async def generic_handler(_: Request, exc: Exception) -> JSONResponse:
        from app.common.logger import logger
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "retryable": False}},
        )
