"""
Adaptive Card renderers for every real-time alert type.

Each function receives the raw alert payload dict from the orchestrator
and returns a fully-formed Adaptive Card dict ready to POST to Graph.

Card design conventions:
  - Header column set: coloured accent bar (2px wide ColumnSet) + icon + title
  - Accent colours per severity:
      warning  → "warning"  (amber)
      info     → "accent"   (blue)
      positive → "good"     (green)
      critical → "attention" (red)
  - Body uses FactSet for structured key/value data
  - Footer: subtle timestamp + "Meeting Analyzer" attribution
  - All cards target Adaptive Cards schema 1.5 (supported in Teams)
"""
from __future__ import annotations

from datetime import datetime, timezone

from mcp.app.config.settings import settings
from typing import Callable

from shared_models.mcp_types import ActionItem

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# Maps alert_type → renderer function
_RENDERERS: dict[str, Callable[[dict], dict]] = {}


def render_alert_card(alert_type: str, payload: dict) -> dict:
    """
    Return a rendered Adaptive Card for the given alert_type and payload.
    Falls back to a generic card if no specific renderer is registered.
    """
    renderer = _RENDERERS.get(alert_type, _generic_card)
    return renderer(payload)


def _register(*types: str):
    """Decorator to register a renderer for one or more alert types."""
    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        for t in types:
            _RENDERERS[t] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
_VERSION = "1.5"

# Emoji icons per alert type (Teams renders these inline)
_ICONS = {
    "off_track": "🔀",
    "agenda_unclear": "❓",
    "agenda_unclear_second": "❗",
    "purpose_detected": "🎯",
    "purpose_drift": "⚠️",
    "tone_private": "🔇",
    "tone_meeting": "⚠️",
    "silent_participant": "🔕",
    "missing_agenda": "📋",
    "time_remaining": "⏱️",
}

_ACCENT_COLOURS = {
    "off_track": "attention",
    "agenda_unclear": "warning",
    "agenda_unclear_second": "attention",
    "purpose_detected": "accent",
    "purpose_drift": "warning",
    "tone_private": "attention",
    "tone_meeting": "attention",
    "silent_participant": "warning",
    "missing_agenda": "warning",
    "time_remaining": "accent",
}


def _base_card(body: list, actions: list | None = None) -> dict:
    card: dict = {
        "$schema": _SCHEMA,
        "type": "AdaptiveCard",
        "version": _VERSION,
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def _header(alert_type: str, title: str) -> dict:
    """Coloured accent bar + icon + title as a ColumnSet."""
    colour = _ACCENT_COLOURS.get(alert_type, "accent")
    icon = _ICONS.get(alert_type, "ℹ️")
    return {
        "type": "ColumnSet",
        "columns": [
            # Thin accent bar
            {
                "type": "Column",
                "width": "4px",
                "style": colour,
                "items": [{"type": "TextBlock", "text": " "}],
            },
            # Icon + title
            {
                "type": "Column",
                "width": "stretch",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{icon}  {title}",
                        "weight": "Bolder",
                        "size": "Medium",
                        "wrap": True,
                        "color": colour,
                    }
                ],
            },
        ],
    }


def _footer() -> dict:
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return {
        "type": "TextBlock",
        "text": f"{settings.app_display_name}  ·  {ts}",
        "size": "Small",
        "color": "Light",
        "isSubtle": True,
        "spacing": "Medium",
    }


def _fact_set(facts: list[tuple[str, str]]) -> dict:
    return {
        "type": "FactSet",
        "facts": [{"title": k, "value": v} for k, v in facts],
        "spacing": "Small",
    }


def _body_text(text: str, subtle: bool = False) -> dict:
    block: dict = {"type": "TextBlock", "text": text, "wrap": True, "spacing": "Small"}
    if subtle:
        block["isSubtle"] = True
    return block


def _bullet_list(items: list[str]) -> list[dict]:
    return [
        {"type": "TextBlock", "text": f"• {item}", "wrap": True, "spacing": "None"}
        for item in items
    ]


# ---------------------------------------------------------------------------
# Per-alert renderers
# ---------------------------------------------------------------------------

@_register("off_track")
def _off_track(p: dict) -> dict:
    score = p.get("max_similarity", 0.0)
    pct = int(score * 100)
    return _base_card([
        _header("off_track", "Discussion Off Track"),
        _body_text(
            "The conversation has drifted away from the meeting agenda "
            "for several consecutive windows."
        ),
        _fact_set([("Agenda relevance", f"{pct}%")]),
        _body_text("Consider steering the discussion back to the agenda.", subtle=True),
        _footer(),
    ])


@_register("agenda_unclear")
def _agenda_unclear(p: dict) -> dict:
    return _base_card([
        _header("agenda_unclear", "Agenda Unclear"),
        _body_text(
            "No clear agenda topic has been identified in the discussion so far."
        ),
        _body_text(
            "Consider sharing the meeting agenda in the chat or stating the objectives clearly.",
            subtle=True,
        ),
        _footer(),
    ])


@_register("agenda_unclear_second")
def _agenda_unclear_second(p: dict) -> dict:
    return _base_card([
        _header("agenda_unclear_second", "Agenda Still Unclear"),
        _body_text(
            "The meeting has been running for several minutes without a clear agenda topic. "
            "Participants may benefit from a brief alignment on objectives."
        ),
        _footer(),
    ])


@_register("purpose_detected")
def _purpose_detected(p: dict) -> dict:
    purpose = p.get("purpose", "Unknown")
    mismatch: bool = p.get("mismatch", False)
    facts = [("Detected purpose", purpose)]
    body = [
        _header("purpose_detected", "Meeting Purpose Identified"),
        _fact_set(facts),
    ]
    if mismatch:
        body.append(_body_text(
            "⚠️ This differs from the calendar invite subject. "
            "You may want to realign expectations.",
        ))
    body.append(_footer())
    return _base_card(body)


@_register("purpose_drift")
def _purpose_drift(p: dict) -> dict:
    return _base_card([
        _header("purpose_drift", "Meeting Purpose Has Drifted"),
        _body_text(
            "The discussion has shifted away from the originally detected meeting purpose "
            "for several consecutive check-ins."
        ),
        _body_text("Consider refocusing or acknowledging the change in direction.", subtle=True),
        _footer(),
    ])


@_register("tone_meeting")
def _tone_meeting(p: dict) -> dict:
    issue_type = p.get("issue_type", "tone issue")
    participant = p.get("participant_name", "A participant")
    severity = p.get("severity", "")
    facts = [
        ("Issue", issue_type.replace("_", " ").title()),
    ]
    if severity:
        facts.append(("Severity", severity))
    return _base_card([
        _header("tone_meeting", "Tone Alert"),
        _body_text(f"{participant}'s communication style may be affecting the meeting dynamic."),
        _fact_set(facts),
        _body_text("Please keep the discussion respectful and constructive.", subtle=True),
        _footer(),
    ])


@_register("tone_private")
def _tone_private(p: dict) -> dict:
    # Private nudge — kept brief and non-accusatory
    issue_type = p.get("issue_type", "tone")
    return _base_card([
        _header("tone_private", "A Note on Communication Style"),
        _body_text(
            f"{settings.app_display_name} noticed your recent messages may come across as {issue_type.replace('_', ' ')}. "
            "This is a private note — no one else can see this."
        ),
        _body_text("Keeping a collaborative tone helps the whole team.", subtle=True),
        _footer(),
    ])


@_register("silent_participant")
def _silent_participant(p: dict) -> dict:
    silent: list[str] = p.get("silent_participants", [])
    body = [
        _header("silent_participant", "Participation Check"),
        _body_text("The following participants haven't spoken recently:"),
    ]
    if silent:
        body += _bullet_list(silent)
    body += [
        _body_text("Consider inviting them to share their thoughts.", subtle=True),
        _footer(),
    ]
    return _base_card(body)


@_register("missing_agenda")
def _missing_agenda(p: dict) -> dict:
    return _base_card([
        _header("missing_agenda", "No Agenda Found"),
        _body_text(
            "This meeting has no agenda items in the calendar invite. "
            "Meetings with a clear agenda tend to be more productive."
        ),
        _body_text("Consider adding agenda items to the calendar event.", subtle=True),
        _footer(),
    ])


@_register("time_remaining")
def _time_remaining(p: dict) -> dict:
    minutes = p.get("minutes_remaining", 0)
    uncovered: list[str] = p.get("uncovered_agenda_topics", [])
    message = p.get("message", f"{minutes} minutes remaining.")

    body = [
        _header("time_remaining", f"⏱️ {minutes} Minute{'s' if minutes != 1 else ''} Remaining"),
        _body_text(message),
    ]

    if uncovered:
        body.append(_body_text("Agenda topics not yet covered:"))
        body += _bullet_list(uncovered)

    body.append(_footer())
    return _base_card(body)


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

def _generic_card(p: dict) -> dict:
    alert_type = p.get("type", "alert")
    title = alert_type.replace("_", " ").title()
    message = p.get("message", "A meeting alert was triggered.")
    return _base_card([
        _header(alert_type, title),
        _body_text(message),
        _footer(),
    ])


# ---------------------------------------------------------------------------
# Poll card (used by create_poll)
# ---------------------------------------------------------------------------

def build_poll_card(action_items: list[ActionItem]) -> dict:
    """Adaptive Card poll for action item confirmation."""
    choices = [
        {"title": f"{item.description}  ({item.owner_name})", "value": item.id}
        for item in action_items
    ]
    return _base_card(
        body=[
            _header("purpose_detected", "Action Item Confirmation"),
            _body_text(
                "Please confirm or dispute the action items captured during this meeting."
            ),
            {
                "type": "Input.ChoiceSet",
                "id": "confirmed_items",
                "isMultiSelect": True,
                "style": "expanded",
                "choices": choices,
                "spacing": "Small",
            },
            _footer(),
        ],
        actions=[
            {
                "type": "Action.Submit",
                "title": "Submit responses",
                "data": {"action": "poll_response"},
            }
        ],
    )
