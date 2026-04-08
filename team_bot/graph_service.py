"""
GraphSubscriptionService — manages Microsoft Graph change notification subscriptions
for online meetings and drives proactive bot join via the Bot Framework.

Flow:
  1. On startup, subscribe() creates a Graph subscription for calendar events
     in the configured tenant. Graph will POST to /api/graph/webhook when a
     meeting is created or updated.
  2. The webhook handler validates the notification, extracts the online meeting
     join URL, and calls proactive_join() to add the bot to the meeting.
  3. A background renewal task calls renew() before the subscription expires
     (Graph subscriptions max out at ~1 hour for online meeting resources).

Authentication:
  Uses client_credentials flow (app-only) with the bot's Azure AD app registration.
  Required Graph permissions (application):
    - OnlineMeetings.Read.All
    - Calendars.Read
    - OnlineMeetings.ReadWrite.All  (to join as bot)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from botbuilder.core import BotFrameworkAdapter
from botbuilder.schema import Activity, ConversationReference

from team_bot.app.config.settings import settings

logger = logging.getLogger("team_bot.graph_service")

# Graph subscription expiry — online meeting resources max at 60 min.
# We renew at 50 min to stay ahead of expiry.
_SUBSCRIPTION_EXPIRY_MINUTES = 60
_RENEWAL_INTERVAL_MINUTES = 50

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class GraphSubscriptionService:
    """
    Manages a Graph change notification subscription and proactive bot join.

    Usage:
        svc = GraphSubscriptionService(settings, adapter)
        await svc.subscribe()           # call once on startup
        await svc.start_renewal_loop()  # keeps subscription alive
        await svc.close()               # on shutdown
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        webhook_url: str,
        webhook_secret: str,
        adapter: BotFrameworkAdapter,
        bot_app_id: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._webhook_url = webhook_url          # public HTTPS URL of /api/graph/webhook
        self._webhook_secret = webhook_secret    # used to validate incoming notifications
        self._adapter = adapter
        self._bot_app_id = bot_app_id

        self._http = httpx.AsyncClient(timeout=30)
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._subscription_id: Optional[str] = None
        self._renewal_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def subscribe(self) -> None:
        """Create a Graph subscription for online meeting events."""
        if not self._is_configured():
            logger.warning(
                "Graph subscription skipped — BOT_GRAPH_TENANT_ID, "
                "BOT_GRAPH_CLIENT_ID, BOT_GRAPH_CLIENT_SECRET, or "
                "BOT_WEBHOOK_BASE_URL not configured."
            )
            return

        token = await self._get_token()
        expiry = (
            datetime.now(timezone.utc) + timedelta(minutes=_SUBSCRIPTION_EXPIRY_MINUTES)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "changeType": "created,updated",
            "notificationUrl": self._webhook_url,
            "resource": "communications/onlineMeetings",
            "expirationDateTime": expiry,
            "clientState": self._webhook_secret,
        }

        resp = await self._http.post(
            f"{_GRAPH_BASE}/subscriptions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code == 201:
            self._subscription_id = resp.json()["id"]
            logger.info("Graph subscription created: %s", self._subscription_id)
        else:
            logger.error(
                "Failed to create Graph subscription: %s %s",
                resp.status_code,
                resp.text,
            )

    async def renew(self) -> None:
        """Extend the subscription expiry before it lapses."""
        if not self._subscription_id:
            await self.subscribe()
            return

        token = await self._get_token()
        expiry = (
            datetime.now(timezone.utc) + timedelta(minutes=_SUBSCRIPTION_EXPIRY_MINUTES)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = await self._http.patch(
            f"{_GRAPH_BASE}/subscriptions/{self._subscription_id}",
            json={"expirationDateTime": expiry},
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code == 200:
            logger.info("Graph subscription renewed: %s", self._subscription_id)
        else:
            logger.warning(
                "Subscription renewal failed (%s) — re-subscribing", resp.status_code
            )
            self._subscription_id = None
            await self.subscribe()

    def start_renewal_loop(self) -> None:
        """Start a background task that renews the subscription periodically."""
        self._renewal_task = asyncio.create_task(self._renewal_loop(), name="graph-renewal")

    @property
    def is_active(self) -> bool:
        """True if a subscription was successfully created."""
        return self._subscription_id is not None

    async def proactive_join(self, meeting_id: str, service_url: str, conversation_id: str) -> None:
        """
        Proactively add the bot to a meeting by continuing a conversation.

        The Bot Framework requires a ConversationReference to send proactive
        messages. We reconstruct one from the meeting metadata received in the
        Graph notification.
        """
        ref = ConversationReference(
            service_url=service_url,
            bot={"id": self._bot_app_id},
            conversation={"id": conversation_id, "isGroup": True},
        )

        async def _callback(turn_context):
            # Sending a simple message causes the bot to appear in the meeting chat.
            # The actual meeting start logic is triggered by the subsequent
            # conversationUpdate/membersAdded activity that Teams sends back.
            await turn_context.send_activity(
                Activity(type="message", text=f"{settings.app_display_name} has joined.")
            )

        try:
            await self._adapter.continue_conversation(
                ref, _callback, self._bot_app_id
            )
            logger.info("Proactive join sent for meeting %s", meeting_id)
        except Exception:
            logger.exception("Proactive join failed for meeting %s", meeting_id)

    async def close(self) -> None:
        if self._renewal_task:
            self._renewal_task.cancel()
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Return a cached app-only access token, refreshing if needed."""
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
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = now + timedelta(seconds=data["expires_in"] - 60)
        return self._token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _renewal_loop(self) -> None:
        while True:
            await asyncio.sleep(_RENEWAL_INTERVAL_MINUTES * 60)
            try:
                await self.renew()
            except Exception:
                logger.exception("Error during subscription renewal")

    def _is_configured(self) -> bool:
        return bool(
            self._tenant_id
            and self._client_id
            and self._client_secret
            and self._webhook_url
            and self._webhook_url.startswith("https://")
        )
