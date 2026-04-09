"""
MCP Protocol handler — implements the Model Context Protocol JSON-RPC interface
so Azure AI Foundry can discover and call tools via MCPTool.

Foundry sends:
  POST /  {"jsonrpc":"2.0","method":"initialize","id":0}
  POST /  {"jsonrpc":"2.0","method":"tools/list","id":1}
  POST /  {"jsonrpc":"2.0","method":"tools/call","params":{"name":"...","arguments":{...}},"id":2}
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("mcp.protocol")

router = APIRouter()

# ---------------------------------------------------------------------------
# Tool definitions — must match the actual REST endpoint schemas exactly
# ---------------------------------------------------------------------------
_TOOLS = [
    {
        "name": "store_transcript_segment",
        "description": "Store a transcript segment for a meeting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "segment": {"type": "object", "description": "TranscriptSegment object"}
            },
            "required": ["segment"],
        },
    },
    {
        "name": "store_meeting_record",
        "description": "Store or update a meeting record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_record": {"type": "object", "description": "MeetingRecord object"}
            },
            "required": ["meeting_record"],
        },
    },
    {
        "name": "get_calendar_event",
        "description": "Get calendar event details for a meeting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"}
            },
            "required": ["meeting_id"],
        },
    },
    {
        "name": "get_analysis_report",
        "description": "Get the analysis report for a meeting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"}
            },
            "required": ["meeting_id"],
        },
    },
    {
        "name": "store_analysis_report",
        "description": "Store the analysis report for a meeting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "object", "description": "AnalysisReport object"}
            },
            "required": ["report"],
        },
    },
    {
        "name": "compute_similarity",
        "description": "Compute similarity between transcript text and agenda topics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"},
                "text": {"type": "string"},
                "agenda_topics": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["meeting_id", "text", "agenda_topics"],
        },
    },
    {
        "name": "send_realtime_alert",
        "description": "Send a real-time alert card to meeting participants.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"},
                "alert_type": {"type": "string"},
                "card_payload": {"type": "object"},
                "target_participant_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["meeting_id", "alert_type", "card_payload"],
        },
    },
    {
        "name": "get_participant_rates",
        "description": "Get participation rates for meeting participants.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "meeting_id": {"type": "string"},
                "participant_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["meeting_id", "participant_ids"],
        },
    },
]

# Map tool name → (HTTP method, internal REST path)
_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "store_transcript_segment": ("POST", "/v1/tools/transcript/store_transcript_segment"),
    "store_meeting_record":     ("POST", "/v1/tools/meeting/store_meeting_record"),
    "get_calendar_event":       ("POST", "/v1/tools/meeting/get_calendar_event"),
    "get_analysis_report":      ("POST", "/v1/tools/analysis/get_analysis_report"),
    "store_analysis_report":    ("POST", "/v1/tools/analysis/store_analysis_report"),
    "compute_similarity":       ("POST", "/v1/tools/similarity/compute_similarity"),
    "send_realtime_alert":      ("POST", "/v1/tools/realtime/send_realtime_alert"),
    "get_participant_rates":    ("POST", "/v1/tools/realtime/get_participant_rates"),
}


def _ok(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _err(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


@router.post("/")
async def mcp_handler(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_err(None, -32700, "Parse error"), status_code=200)

    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params", {})

    logger.debug("MCP protocol: method=%s id=%s", method, req_id)

    if method == "initialize":
        return JSONResponse(_ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "meeting-bot-mcp-server", "version": "1.0.0"},
        }))

    if method == "notifications/initialized":
        return JSONResponse(_ok(req_id, {}))

    if method == "tools/list":
        return JSONResponse(_ok(req_id, {"tools": _TOOLS}))

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in _TOOL_ROUTES:
            return JSONResponse(_err(req_id, -32601, f"Unknown tool: {tool_name}"))

        http_method, path = _TOOL_ROUTES[tool_name]
        base_url = str(request.base_url).rstrip("/")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method=http_method,
                    url=f"{base_url}{path}",
                    json=arguments,
                )
            if resp.status_code in (200, 201, 204):
                content = resp.json() if resp.content else {}
                return JSONResponse(_ok(req_id, {
                    "content": [{"type": "text", "text": json.dumps(content)}]
                }))
            else:
                logger.warning("MCP tool %s failed: %d %s", tool_name, resp.status_code, resp.text[:200])
                return JSONResponse(_err(req_id, -32603, f"Tool error {resp.status_code}: {resp.text[:200]}"))
        except Exception as exc:
            logger.exception("MCP tool call failed: %s", tool_name)
            return JSONResponse(_err(req_id, -32603, str(exc)))

    return JSONResponse(_err(req_id, -32601, f"Method not found: {method}"))
