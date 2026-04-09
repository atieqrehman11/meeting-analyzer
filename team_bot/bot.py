from __future__ import annotations

import logging
from typing import Any, Callable

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes

from shared_models.mcp_client import BaseMcpClient
from team_bot.app.config.settings import settings

logger = logging.getLogger("team_bot.bot")


class MeetingOrchestratorManager:
    """Tracks active meeting orchestrators and routes lifecycle events."""

    def __init__(
        self,
        orchestrator_factory: Callable[
            [str, list[dict[str, Any]]], tuple[object, BaseMcpClient]
        ],
    ) -> None:
        self._orchestrator_factory = orchestrator_factory
        self._active_meetings: dict[str, tuple[object, BaseMcpClient]] = {}

    async def start_meeting(self, meeting_id: str, participant_roster: list[dict[str, Any]]) -> None:
        if meeting_id in self._active_meetings:
            logger.info("[MEETING] Already active — skipping start: %s", meeting_id)
            return

        logger.info("[MEETING] Starting meeting: %s (participants: %d)", meeting_id, len(participant_roster))
        orchestrator, mcp_client = self._orchestrator_factory(meeting_id, participant_roster)
        self._active_meetings[meeting_id] = (orchestrator, mcp_client)

        logger.info("[MEETING] Orchestrator created, calling on_meeting_start: %s", meeting_id)
        await orchestrator.on_meeting_start(meeting_id, participant_roster)
        logger.info("[MEETING] on_meeting_start complete: %s", meeting_id)

    async def end_meeting(self, meeting_id: str) -> None:
        pair = self._active_meetings.pop(meeting_id, None)
        if pair is None:
            logger.warning("[MEETING] end_meeting called but no active meeting found: %s", meeting_id)
            return

        orchestrator, mcp_client = pair
        logger.info("[MEETING] Ending meeting: %s", meeting_id)
        await orchestrator.on_meeting_end(meeting_id)
        logger.info("[MEETING] on_meeting_end complete, closing MCP client: %s", meeting_id)
        await mcp_client.aclose()
        logger.info("[MEETING] Meeting fully closed: %s", meeting_id)

    async def shutdown(self) -> None:
        for meeting_id in list(self._active_meetings):
            await self.end_meeting(meeting_id)


class TeamsMeetingBot(ActivityHandler):
    """Teams bot entrypoint for lifecycle events and consent routing."""

    def __init__(self, manager: MeetingOrchestratorManager) -> None:
        self._manager = manager
        self._welcomed_meetings: set[str] = set()  # prevent duplicate welcome messages

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        text = self._strip_mention(turn_context).lower()
        activity = turn_context.activity
        meeting_id = self._extract_meeting_id(activity)

        # Auto-start orchestrator on first message in a meeting chat
        if meeting_id and meeting_id not in self._manager._active_meetings:
            logger.info("[EVENT] First message in meeting chat — auto-starting orchestrator: %s", meeting_id)
            participant_roster = self._extract_participant_roster(activity)
            await self._manager.start_meeting(meeting_id, participant_roster)
            if meeting_id not in self._welcomed_meetings:
                self._welcomed_meetings.add(meeting_id)
                await turn_context.send_activity(
                    settings.msg_welcome.format(name=settings.app_display_name)
                )

        if not text:
            return
        response = self._get_command_response(text)
        await turn_context.send_activity(response)

    def _strip_mention(self, turn_context: TurnContext) -> str:
        """Remove bot @mention prefix from message text."""
        text = (turn_context.activity.text or "").strip()
        bot_id = turn_context.activity.recipient.id
        for entity in turn_context.activity.entities or []:
            if getattr(entity, "type", None) != "mention":
                continue
            if getattr(getattr(entity, "mentioned", None), "id", None) == bot_id:
                mention_text = getattr(entity, "text", "") or ""
                text = text.replace(mention_text, "").strip()
        return text

    def _get_command_response(self, text: str) -> str:
        """Return the appropriate response string for a given command."""
        name = settings.app_display_name
        if text in ("help", "/help"):
            return settings.msg_help.format(name=name)
        if text in ("status", "/status"):
            return settings.msg_status.format(name=name)
        return settings.msg_default.format(name=name)

    async def on_conversation_update_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        meeting_id = self._extract_meeting_id(activity)

        logger.info(
            "[EVENT] conversationUpdate — meeting_id=%s members_added=%s members_removed=%s",
            meeting_id,
            [getattr(m, "id", None) for m in (activity.members_added or [])],
            [getattr(m, "id", None) for m in (activity.members_removed or [])],
        )

        if activity.members_added and self._bot_joined(activity.members_added, activity.recipient.id):
            if meeting_id:
                meeting_in_progress = self._is_meeting_in_progress(activity)
                logger.info("[EVENT] Bot joined meeting chat — in_progress=%s meeting_id=%s", meeting_in_progress, meeting_id)
                if meeting_id not in self._welcomed_meetings:
                    self._welcomed_meetings.add(meeting_id)
                    await turn_context.send_activity(
                        settings.msg_welcome.format(name=settings.app_display_name)
                    )
                else:
                    logger.debug("[EVENT] Welcome already sent for meeting %s — skipping", meeting_id)
                if meeting_in_progress:
                    participant_roster = self._extract_participant_roster(activity)
                    await self._manager.start_meeting(meeting_id, participant_roster)
                else:
                    logger.info("[EVENT] Meeting not yet started — orchestrator will start on meetingStart event")
            else:
                logger.info("[EVENT] Bot added to non-meeting chat — skipping")

        elif activity.members_added:
            logger.info("[EVENT] Participant(s) joined meeting %s", meeting_id)

        if activity.members_removed and self._bot_left(activity.members_removed, activity.recipient.id):
            logger.info("[EVENT] Bot removed from meeting chat — triggering end_meeting: %s", meeting_id)
            await self._manager.end_meeting(meeting_id)

    async def on_event_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        meeting_id = self._extract_meeting_id(activity)

        logger.info("[EVENT] event activity — name=%s meeting_id=%s", activity.name, meeting_id)

        if activity.name == "meetingStart":
            logger.info("[EVENT] meetingStart received — starting orchestrator: %s", meeting_id)
            if meeting_id:
                participant_roster = self._extract_participant_roster(activity)
                await self._manager.start_meeting(meeting_id, participant_roster)
        elif activity.name == "meetingEnd":
            logger.info("[EVENT] meetingEnd received — ending orchestrator: %s", meeting_id)
            if meeting_id:
                await self._manager.end_meeting(meeting_id)
        elif activity.name == "participantJoined":
            logger.info("[EVENT] Participant joined meeting %s", meeting_id)
        elif activity.name == "participantLeft":
            logger.info("[EVENT] Participant left meeting %s", meeting_id)
        elif activity.name in ("endOfConversation",):
            logger.info("[EVENT] endOfConversation — ending orchestrator: %s", meeting_id)
            if meeting_id:
                await self._manager.end_meeting(meeting_id)

    async def on_end_of_conversation_activity(self, turn_context: TurnContext) -> None:
        meeting_id = self._extract_meeting_id(turn_context.activity)
        logger.info("[EVENT] endOfConversation activity — meeting_id=%s", meeting_id)
        if meeting_id:
            await self._manager.end_meeting(meeting_id)

    def _is_meeting_in_progress(self, activity: Activity) -> bool:
        """Check if the meeting is currently active via channelData."""
        channel_data = getattr(activity, "channel_data", {}) or {}
        meeting = channel_data.get("meeting") or {}
        conv = getattr(activity, "conversation", None)
        conv_type = getattr(conv, "conversation_type", "") or ""
        logger.debug("[EVENT] _is_meeting_in_progress — meeting=%s conv_type=%s channel_data_keys=%s",
                     meeting, conv_type, list(channel_data.keys()))
        return bool(meeting.get("id"))

    def _extract_meeting_id(self, activity: Activity) -> str | None:
        channel_data = getattr(activity, "channel_data", {}) or {}
        meeting = channel_data.get("meeting") or {}
        return meeting.get("id") or activity.conversation.id

    def _extract_participant_roster(self, activity: Activity) -> list[dict[str, Any]]:
        channel_data = getattr(activity, "channel_data", {}) or {}
        roster = []

        participants = channel_data.get("participants") or []
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            roster.append(
                {
                    "id": participant.get("id"),
                    "display_name": participant.get("name"),
                    "tenant_id": participant.get("tenantId"),
                    "role": participant.get("role"),
                }
            )

        return roster

    def _bot_joined(self, members_added: list[ActivityTypes], bot_id: str) -> bool:
        return any(getattr(member, "id", None) == bot_id for member in members_added)

    def _bot_left(self, members_removed: list[ActivityTypes], bot_id: str) -> bool:
        return any(getattr(member, "id", None) == bot_id for member in members_removed)
