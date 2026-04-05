"""
Real Microsoft Graph API backend.
Uses app-only (client_credentials) auth with httpx.
Required Graph application permissions:
  - OnlineMeetings.Read.All
  - Calendars.Read
  - OnlineMeetings.ReadWrite.All
  - Chat.ReadWrite.All  (for adaptive cards / chat messages)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from shared_models.mcp_types import ActionItem
from .base import GraphBackend
from .cards import render_alert_card, build_poll_card
from app.common.logger import logger

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class AzureGraphBackend(GraphBackend):
    """
    GraphBackend backed by real Microsoft Graph API calls.

    meeting_id is expected to be the Teams online meeting ID
    (e.g. the value from onlineMeeting.id or the joinWebUrl-derived ID).
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = httpx.AsyncClient(timeout=30)
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # GraphBackend interface
    # ------------------------------------------------------------------

    async def get_calendar_event(self, meeting_id: str) -> dict:
        """
        Fetch an online meeting by its ID and map it to CalendarEventOutput shape.
        Graph endpoint: GET /me/onlineMeetings/{meetingId}
        Falls back to /communications/onlineMeetings/{meetingId} for app-only.
        """
        token = await self._get_token()
        resp = await self._http.get(
            f"{_GRAPH_BASE}/communications/onlineMeetings/{meeting_id}",
            headers=self._auth_headers(token),
        )
        resp.raise_for_status()
        data = resp.json()

        body_text: str = ""
        if data.get("joinInformation"):
            body_text = data["joinInformation"].get("content", "")

        agenda = _extract_agenda(body_text or data.get("subject", ""))

        organizer = data.get("participants", {}).get("organizer", {})
        organizer_identity = organizer.get("identity", {}).get("user", {})

        return {
            "meeting_id": meeting_id,
            "subject": data.get("subject", ""),
            "description": body_text or None,
            "agenda": agenda,
            "start_time": data.get("startDateTime", ""),
            "end_time": data.get("endDateTime", ""),
            "organizer_id": organizer_identity.get("id", ""),
            "organizer_name": organizer_identity.get("displayName", ""),
        }

    async def get_recording_status(self, meeting_id: str) -> bool:
        """
        Check whether recording is enabled for the meeting.
        Graph endpoint: GET /communications/onlineMeetings/{meetingId}
        Uses the recordingStatus field when available.
        """
        token = await self._get_token()
        resp = await self._http.get(
            f"{_GRAPH_BASE}/communications/onlineMeetings/{meeting_id}",
            headers=self._auth_headers(token),
            params={"$select": "id,recordingStatus"},
        )
        resp.raise_for_status()
        data = resp.json()
        # recordingStatus: "notStarted" | "recording" | "failed" | "unknownFutureValue"
        return data.get("recordingStatus") == "recording"

    async def post_adaptive_card(
        self,
        meeting_id: str,
        card: dict,
        target_ids: Optional[list[str]],
    ) -> None:
        """
        Post a pre-built adaptive card to the meeting group chat.
        target_ids is accepted for interface compatibility but individual
        delivery is not implemented — all cards go to the meeting chat thread.
        """
        chat_id = await self._get_meeting_chat_id(meeting_id)
        token = await self._get_token()
        message_body = _wrap_card(card)
        await self._post_chat_message(chat_id, message_body, token)
        logger.info("GraphBackend: posted adaptive card to meeting chat %s", chat_id)

    async def send_realtime_alert(
        self,
        meeting_id: str,
        alert_type: str,
        card: dict,
        target_ids: Optional[list[str]],
    ) -> None:
        """
        Render a typed alert card and post it to the meeting group chat.
        The raw orchestrator payload is passed to the card renderer which
        produces a properly formatted Adaptive Card for each alert type.
        """
        rendered = render_alert_card(alert_type, card)
        chat_id = await self._get_meeting_chat_id(meeting_id)
        token = await self._get_token()
        await self._post_chat_message(chat_id, _wrap_card(rendered), token)
        logger.info(
            "GraphBackend: sent %s alert to meeting chat %s", alert_type, chat_id
        )

    async def create_poll(self, meeting_id: str, action_items: list[ActionItem]) -> str:
        """
        Post an action item confirmation poll card to the meeting chat.
        Returns the Graph message ID as the poll_id.
        """
        chat_id = await self._get_meeting_chat_id(meeting_id)
        token = await self._get_token()
        poll_card = build_poll_card(action_items)
        resp = await self._post_chat_message(chat_id, _wrap_card(poll_card), token)
        poll_id = resp.get("id", f"poll-{meeting_id}")
        logger.info("GraphBackend: created poll %s in chat %s", poll_id, chat_id)
        return poll_id

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._token and self._token_expiry and now < self._token_expiry:
                return self._token

            url = _TOKEN_URL.format(tenant_id=self._tenant_id)
            resp = await self._http.post(url, data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
            })
            resp.raise_for_status()
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expiry = now + timedelta(seconds=payload["expires_in"] - 60)
            logger.debug("GraphBackend: acquired new access token")
            return self._token

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def _get_meeting_chat_id(self, meeting_id: str) -> str:
        """Resolve the Teams chat thread ID for a given online meeting ID."""
        token = await self._get_token()
        resp = await self._http.get(
            f"{_GRAPH_BASE}/communications/onlineMeetings/{meeting_id}",
            headers=self._auth_headers(token),
            params={"$select": "id,chatInfo"},
        )
        resp.raise_for_status()
        data = resp.json()
        chat_id = data.get("chatInfo", {}).get("threadId")
        if not chat_id:
            raise ValueError(f"No chatInfo.threadId found for meeting {meeting_id}")
        return chat_id

    async def _post_chat_message(self, chat_id: str, body: dict, token: str) -> dict:
        resp = await self._http.post(
            f"{_GRAPH_BASE}/chats/{chat_id}/messages",
            json=body,
            headers=self._auth_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

def _wrap_card(card: dict) -> dict:
    """Wrap an Adaptive Card dict in a Graph chat message envelope."""
    return {
        "body": {
            "contentType": "html",
            "content": '<attachment id="card"></attachment>',
        },
        "attachments": [
            {
                "id": "card",
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


def _extract_agenda(text: str) -> list[str]:
    """Best-effort extraction of agenda items from meeting body text."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Look for numbered or bulleted lines after an "Agenda" heading
    agenda: list[str] = []
    in_agenda = False
    for line in lines:
        if "agenda" in line.lower():
            in_agenda = True
            continue
        if in_agenda:
            # Stop at blank section or new heading
            if line.startswith("#") or (len(line) > 60 and not line[0].isdigit()):
                break
            cleaned = line.lstrip("0123456789.-) ").strip()
            if cleaned:
                agenda.append(cleaned)
    return agenda

