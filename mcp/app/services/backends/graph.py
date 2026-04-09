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
        Fetch an online meeting by its thread ID.
        The meeting_id from Teams is a base64-encoded thread ID.
        We decode it to get the thread ID and look up via chats endpoint.
        """
        token = await self._get_token()

        # Decode the Teams meeting ID to get the thread ID
        thread_id = self._decode_meeting_id(meeting_id)
        logger.debug("GraphBackend.get_calendar_event: meeting_id=%s decoded_thread=%s", meeting_id, thread_id)

        # Get meeting info via the chat thread
        resp = await self._http.get(
            f"{_GRAPH_BASE}/chats/{thread_id}",
            headers=self._auth_headers(token),
            params={"$select": "id,topic,onlineMeetingInfo"},
        )
        logger.debug("GraphBackend: GET /chats/%s status=%d body=%s", thread_id, resp.status_code, resp)

        if resp.status_code == 200:
            chat_data = resp.json()
            meeting_info = chat_data.get("onlineMeetingInfo") or {}
            join_url = meeting_info.get("joinWebUrl", "")
            organizer_id = meeting_info.get("organizer", {}).get("id", "") if meeting_info.get("organizer") else ""
            logger.debug("GraphBackend: chat topic=%s join_url=%s organizer=%s",
                         chat_data.get("topic"), join_url[:60], organizer_id)

            if join_url and organizer_id:
                import urllib.parse
                # Use the URL as-is (URL-encoded) — Graph stores it this way
                base_join_url = join_url.split("?")[0]  # strip context params
                meet_resp = await self._http.get(
                    f"{_GRAPH_BASE}/users/{organizer_id}/onlineMeetings",
                    headers=self._auth_headers(token),
                    params={"$filter": f"joinWebUrl eq '{base_join_url}'"},
                )
                logger.debug("GraphBackend: user onlineMeetings filter status=%d body=%s",
                             meet_resp.status_code, meet_resp.text[:300])
                if meet_resp.status_code == 200:
                    items = meet_resp.json().get("value", [])
                    if items:
                        return self._map_meeting_data(meeting_id, items[0])

            # Fallback: build from chat data + messages
            logger.warning("GraphBackend: using chat fallback for meeting %s", meeting_id)
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            subject = chat_data.get("topic") or "Teams Meeting"

            # Try to get agenda and times from chat messages
            extra = await self._get_meeting_details_from_messages(thread_id, token)
            agenda = extra.get("agenda") or _extract_agenda(subject)
            description = extra.get("description")

            return {
                "meeting_id": meeting_id,
                "subject": subject,
                "description": description,
                "agenda": agenda,
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
                "organizer_id": organizer_id,
                "organizer_name": "",
            }

        # Fallback — return minimal record with current time
        logger.warning("GraphBackend: could not fetch meeting details for %s — using fallback", meeting_id)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        return {
            "meeting_id": meeting_id,
            "subject": "Teams Meeting",
            "description": None,
            "agenda": [],
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(),
            "organizer_id": "",
            "organizer_name": "",
        }
    def _map_from_chat(self, meeting_id: str, chat_data: dict) -> dict:
        """Build a CalendarEventOutput from chat data when onlineMeetings API is unavailable."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        subject = chat_data.get("topic") or "Teams Meeting"
        agenda = _extract_agenda(subject)
        return {
            "meeting_id": meeting_id,
            "subject": subject,
            "description": None,
            "agenda": agenda,
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=1)).isoformat(),
            "organizer_id": "",
            "organizer_name": "",
        }

    async def _get_meeting_details_from_messages(self, thread_id: str, token: str) -> dict:
        """
        Extract meeting start/end time and agenda from chat system messages.
        Teams posts a system message with meeting details when the meeting is created.
        """
        resp = await self._http.get(
            f"{_GRAPH_BASE}/chats/{thread_id}/messages",
            headers=self._auth_headers(token),
            params={"$top": "10", "$orderby": "createdDateTime asc"},
        )
        logger.debug("GraphBackend: chat messages status=%d", resp.status_code)
        if resp.status_code != 200:
            return {}

        messages = resp.json().get("value", [])
        for msg in messages:
            # System messages contain meeting metadata in eventDetail
            event_detail = msg.get("eventDetail") or {}
            msg_type = event_detail.get("@odata.type", "")

            if "callStarted" in msg_type or "meetingPolicyViolation" in msg_type:
                continue

            # Meeting invite system message contains start/end times
            if event_detail.get("callDuration") or event_detail.get("callEventType"):
                continue

            # Look for meeting created/updated event with time info
            body_content = (msg.get("body") or {}).get("content", "")
            if body_content and ("start" in body_content.lower() or "agenda" in body_content.lower()):
                agenda = _extract_agenda(body_content)
                if agenda:
                    logger.debug("GraphBackend: extracted agenda from chat messages: %s", agenda)
                    return {"agenda": agenda, "description": body_content}

        return {}

    def _decode_meeting_id(self, meeting_id: str) -> str:
        """Extract the Teams thread ID from the base64-encoded meeting ID."""
        import base64
        try:
            # Strip the MCM prefix and #0 suffix, decode base64
            stripped = meeting_id.lstrip("MCM")
            # Add padding if needed
            padded = stripped + "=" * (4 - len(stripped) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            # Format: 19:meeting_xxx@thread.v2
            if "@thread" in decoded:
                return decoded.split("#")[0]
        except Exception:
            pass
        return meeting_id

    def _map_meeting_data(self, meeting_id: str, data: dict) -> dict:
        """Map Graph onlineMeeting response to CalendarEventOutput shape."""
        body_text = ""
        if data.get("joinInformation"):
            body_text = data["joinInformation"].get("content", "")
        agenda = _extract_agenda(body_text or data.get("subject", ""))

        # Graph returns UTC times without timezone suffix — normalise to UTC ISO
        def _ensure_utc(dt_str: str) -> str:
            if not dt_str:
                return dt_str
            if not dt_str.endswith("Z") and "+" not in dt_str:
                dt_str += "Z"
            return dt_str.replace("Z", "+00:00")

        organizer = data.get("participants", {}).get("organizer", {})
        organizer_identity = organizer.get("identity", {}).get("user", {})
        result = {
            "meeting_id": meeting_id,
            "subject": data.get("subject", ""),
            "description": body_text or None,
            "agenda": agenda,
            "start_time": _ensure_utc(data.get("startDateTime", "")),
            "end_time": _ensure_utc(data.get("endDateTime", "")),
            "organizer_id": organizer_identity.get("id", ""),
            "organizer_name": organizer_identity.get("displayName", ""),
        }
        logger.debug("GraphBackend: mapped meeting data=%s", result)
        return result

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
        """Resolve the Teams chat thread ID from the meeting ID."""
        thread_id = self._decode_meeting_id(meeting_id)
        if thread_id != meeting_id:
            logger.debug("GraphBackend: resolved chat_id=%s from meeting_id=%s", thread_id, meeting_id)
            return thread_id
        # Fallback: try Graph chats endpoint
        token = await self._get_token()
        resp = await self._http.get(
            f"{_GRAPH_BASE}/chats/{meeting_id}",
            headers=self._auth_headers(token),
            params={"$select": "id,onlineMeetingInfo"},
        )
        resp.raise_for_status()
        data = resp.json()
        chat_id = data.get("id") or meeting_id
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

