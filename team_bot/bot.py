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
            logger.info("Meeting %s is already active", meeting_id)
            return

        orchestrator, mcp_client = self._orchestrator_factory(meeting_id, participant_roster)
        self._active_meetings[meeting_id] = (orchestrator, mcp_client)

        logger.info("Starting orchestrator for meeting %s", meeting_id)
        await orchestrator.on_meeting_start(meeting_id, participant_roster)

    async def end_meeting(self, meeting_id: str) -> None:
        pair = self._active_meetings.pop(meeting_id, None)
        if pair is None:
            logger.warning("No active meeting found for %s", meeting_id)
            return

        orchestrator, mcp_client = pair
        logger.info("Ending orchestrator for meeting %s", meeting_id)
        await orchestrator.on_meeting_end(meeting_id)
        await mcp_client.aclose()

    async def shutdown(self) -> None:
        for meeting_id in list(self._active_meetings):
            await self.end_meeting(meeting_id)


class TeamsMeetingBot(ActivityHandler):
    """Teams bot entrypoint for lifecycle events and consent routing."""

    def __init__(self, manager: MeetingOrchestratorManager) -> None:
        self._manager = manager

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        text = self._strip_mention(turn_context).lower()
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

        if activity.members_added and self._bot_joined(activity.members_added, activity.recipient.id):
            # Only send welcome and start meeting if this is a meeting context
            if meeting_id:
                await turn_context.send_activity(
                    settings.msg_welcome.format(name=settings.app_display_name)
                )
                participant_roster = self._extract_participant_roster(activity)
                await self._manager.start_meeting(meeting_id, participant_roster)
            else:
                logger.info("Bot added to non-meeting chat — skipping welcome")

        elif activity.members_added:
            logger.info("Participant joined meeting %s", meeting_id)

        if activity.members_removed and self._bot_left(activity.members_removed, activity.recipient.id):
            await self._manager.end_meeting(meeting_id)

    async def on_event_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        if activity.name == "participantJoined":
            meeting_id = self._extract_meeting_id(activity)
            logger.info("Late joiner event for meeting %s", meeting_id)
            # Late joiner consent flow should be implemented here.
        elif activity.name == "participantLeft":
            meeting_id = self._extract_meeting_id(activity)
            logger.info("Participant left event for meeting %s", meeting_id)

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
