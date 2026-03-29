from __future__ import annotations

import logging
from typing import Any, Callable

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes

from shared_models.mcp_client import BaseMcpClient

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
        await turn_context.send_activity(
            "Meeting Analyzer bot received your message. "
            "This service is a TeamsBot entrypoint for lifecycle and consent events."
        )

    async def on_conversation_update_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        meeting_id = self._extract_meeting_id(activity)
        if not meeting_id:
            logger.warning("Conversation update event missing meeting id")
            return

        if activity.members_added:
            if self._bot_joined(activity.members_added, activity.recipient.id):
                participant_roster = self._extract_participant_roster(activity)
                await self._manager.start_meeting(meeting_id, participant_roster)
            else:
                logger.info("Participant joined meeting %s", meeting_id)

        if activity.members_removed:
            if self._bot_left(activity.members_removed, activity.recipient.id):
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
