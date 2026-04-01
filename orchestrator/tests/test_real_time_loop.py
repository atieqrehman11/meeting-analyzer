"""
Unit tests for RealTimeLoop.

All MCP calls are mocked — no in-process server needed here.
The loop's run() is never awaited directly; individual methods are tested.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.config import OrchestratorConfig
from orchestrator.real_time_loop import RealTimeLoop
from shared_models.mcp_client import McpCallError
from shared_models.mcp_types import MeetingRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> OrchestratorConfig:
    defaults = dict(
        realtime_loop_interval_seconds=60,
        realtime_loop_start_delay_seconds=0,
        off_track_consecutive_windows=3,
        off_track_similarity_threshold=0.35,
        agenda_unclear_threshold=0.4,
        agenda_unclear_trigger_minutes=5,
        agenda_unclear_second_alert_minutes=8,
        alert_throttle_window_seconds=300,
        participation_pulse_interval_minutes=5,
        silent_participant_threshold_minutes=10,
        purpose_detection_delay_seconds=120,
        purpose_recheck_interval_minutes=5,
        purpose_drift_consecutive_minutes=5,
    )
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def _record(agenda=None, participants=None) -> MeetingRecord:
    return MeetingRecord(
        id="meeting_mtg-rt-001",
        meeting_id="mtg-rt-001",
        organizer_id="org-1",
        organizer_name="Alice",
        subject="RT Test",
        start_time="2026-01-01T10:00:00Z",
        created_at="2026-01-01T09:55:00Z",
        updated_at="2026-01-01T09:55:00Z",
        azure_region="eastus",
        retention_expires_at="2026-04-01T00:00:00Z",
        agenda=agenda if agenda is not None else ["Budget review", "Roadmap"],
        participants=participants if participants is not None else ["p-1", "p-2"],
    )


def _mcp(similarity_score=0.8) -> MagicMock:
    mcp = MagicMock()
    mcp.compute_similarity = AsyncMock(return_value=MagicMock(
        max_score=similarity_score,
        scores=[],
    ))
    mcp.send_realtime_alert = AsyncMock()
    mcp.get_participant_rates = AsyncMock(return_value=MagicMock(rates=[]))
    return mcp


def _loop(mcp=None, cfg=None, record=None, agenda=None) -> RealTimeLoop:
    r = record or _record()
    return RealTimeLoop(
        meeting_id="mtg-rt-001",
        record=r,
        mcp=mcp or _mcp(),
        cfg=cfg or _cfg(),
        agenda=agenda if agenda is not None else ["Budget review", "Roadmap"],
    )


# ---------------------------------------------------------------------------
# Agenda adherence — similarity check
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agenda_adherence_calls_compute_similarity():
    mcp = _mcp(similarity_score=0.9)
    loop = _loop(mcp=mcp)
    await loop._check_agenda_adherence()
    mcp.compute_similarity.assert_awaited_once()


@pytest.mark.anyio
async def test_agenda_adherence_skips_when_no_agenda():
    mcp = _mcp()
    loop = _loop(mcp=mcp, agenda=[])
    await loop._check_agenda_adherence()
    mcp.compute_similarity.assert_not_awaited()


@pytest.mark.anyio
async def test_agenda_adherence_buffers_scores():
    loop = _loop(mcp=_mcp(similarity_score=0.5))
    await loop._check_agenda_adherence()
    await loop._check_agenda_adherence()
    assert len(loop._similarity_buffer) == 2


@pytest.mark.anyio
async def test_agenda_adherence_buffer_capped_at_window_size():
    cfg = _cfg(off_track_consecutive_windows=3)
    loop = _loop(mcp=_mcp(similarity_score=0.5), cfg=cfg)
    for _ in range(10):
        await loop._check_agenda_adherence()
    assert len(loop._similarity_buffer) == 3


@pytest.mark.anyio
async def test_off_track_alert_sent_when_all_windows_below_threshold():
    cfg = _cfg(
        off_track_consecutive_windows=3,
        off_track_similarity_threshold=0.35,
        alert_throttle_window_seconds=0,  # disable throttle
    )
    mcp = _mcp(similarity_score=0.1)  # always below threshold
    loop = _loop(mcp=mcp, cfg=cfg)

    # Fill the buffer
    for _ in range(3):
        await loop._check_agenda_adherence()

    mcp.send_realtime_alert.assert_awaited()
    alert_types = [c.args[1] for c in mcp.send_realtime_alert.await_args_list]
    assert "off_track" in alert_types


@pytest.mark.anyio
async def test_off_track_alert_not_sent_when_score_above_threshold():
    cfg = _cfg(
        off_track_consecutive_windows=3,
        off_track_similarity_threshold=0.35,
        alert_throttle_window_seconds=0,
    )
    mcp = _mcp(similarity_score=0.9)  # always above threshold
    loop = _loop(mcp=mcp, cfg=cfg)

    for _ in range(3):
        await loop._check_agenda_adherence()

    alert_types = [c.args[1] for c in mcp.send_realtime_alert.await_args_list]
    assert "off_track" not in alert_types


@pytest.mark.anyio
async def test_similarity_mcp_error_is_swallowed():
    mcp = _mcp()
    mcp.compute_similarity = AsyncMock(
        side_effect=McpCallError("TRANSPORT_ERROR", "down", retryable=True)
    )
    loop = _loop(mcp=mcp)
    # Should not raise
    await loop._check_agenda_adherence()
    assert loop._similarity_buffer == []


# ---------------------------------------------------------------------------
# Alert throttling
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_throttled_alert_suppressed_within_window():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(alert_throttle_window_seconds=300))
    await loop._send_throttled_alert("off_track", {})
    await loop._send_throttled_alert("off_track", {})  # should be suppressed
    assert mcp.send_realtime_alert.await_count == 1


@pytest.mark.anyio
async def test_throttled_alert_sent_after_window_expires():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(alert_throttle_window_seconds=0))
    await loop._send_throttled_alert("off_track", {})
    await loop._send_throttled_alert("off_track", {})
    assert mcp.send_realtime_alert.await_count == 2


@pytest.mark.anyio
async def test_different_alert_types_not_throttled_together():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(alert_throttle_window_seconds=300))
    await loop._send_throttled_alert("off_track", {})
    await loop._send_throttled_alert("agenda_unclear", {})
    assert mcp.send_realtime_alert.await_count == 2


@pytest.mark.anyio
async def test_alert_mcp_error_is_swallowed():
    mcp = _mcp()
    mcp.send_realtime_alert = AsyncMock(
        side_effect=McpCallError("GRAPH_DOWN", "unavailable", retryable=True)
    )
    loop = _loop(mcp=mcp)
    # Should not raise
    await loop._send_alert("off_track", {})


# ---------------------------------------------------------------------------
# Purpose detection
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_purpose_not_detected_before_delay():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(purpose_detection_delay_seconds=9999))
    now = time.monotonic()
    await loop._check_purpose(now)
    mcp.send_realtime_alert.assert_not_awaited()
    assert not loop._purpose_detected


@pytest.mark.anyio
async def test_purpose_detected_after_delay():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(purpose_detection_delay_seconds=0))
    now = time.monotonic()
    # First call sets the scheduled time
    await loop._check_purpose(now)
    # Second call fires detection (scheduled_at <= now)
    await loop._check_purpose(now + 1)
    assert loop._purpose_detected
    mcp.send_realtime_alert.assert_awaited()


@pytest.mark.anyio
async def test_purpose_detected_only_once():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(purpose_detection_delay_seconds=0))
    now = time.monotonic()
    await loop._check_purpose(now)
    await loop._check_purpose(now + 1)  # fires
    await loop._check_purpose(now + 2)  # should not fire again
    # send_realtime_alert called once for purpose_detected
    purpose_calls = [c for c in mcp.send_realtime_alert.await_args_list
                     if c.args[1] == "purpose_detected"]
    assert len(purpose_calls) == 1


# ---------------------------------------------------------------------------
# Participation pulse
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_participation_pulse_skipped_before_interval():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(participation_pulse_interval_minutes=5))
    now = time.monotonic()
    loop._last_pulse_at = now  # just fired
    await loop._check_participation_pulse(now + 10)  # only 10s later
    mcp.get_participant_rates.assert_not_awaited()


@pytest.mark.anyio
async def test_participation_pulse_fires_after_interval():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(participation_pulse_interval_minutes=5))
    now = time.monotonic()
    loop._last_pulse_at = now - 400  # 400s ago > 300s interval
    await loop._check_participation_pulse(now)
    mcp.get_participant_rates.assert_awaited_once()


@pytest.mark.anyio
async def test_participation_pulse_increments_snapshot_count():
    mcp = _mcp()
    loop = _loop(mcp=mcp, cfg=_cfg(participation_pulse_interval_minutes=5))
    now = time.monotonic()
    loop._last_pulse_at = now - 400
    await loop._check_participation_pulse(now)
    assert loop._pulse_snapshot_count == 1


@pytest.mark.anyio
async def test_participation_pulse_mcp_error_is_swallowed():
    mcp = _mcp()
    mcp.get_participant_rates = AsyncMock(
        side_effect=McpCallError("TRANSPORT_ERROR", "down", retryable=True)
    )
    loop = _loop(mcp=mcp, cfg=_cfg(participation_pulse_interval_minutes=5))
    loop._last_pulse_at = None
    # Should not raise
    await loop._check_participation_pulse(time.monotonic())


@pytest.mark.anyio
async def test_participation_pulse_skipped_with_no_participants():
    mock_mcp = _mcp()
    rec = _record(participants=[])
    loop = RealTimeLoop(
        meeting_id="mtg-rt-001",
        record=rec,
        mcp=mock_mcp,
        cfg=_cfg(participation_pulse_interval_minutes=5),
        agenda=[],
    )
    loop._last_pulse_at = None
    await loop._check_participation_pulse(time.monotonic())
    mock_mcp.get_participant_rates.assert_not_awaited()


# ---------------------------------------------------------------------------
# Time remaining alert
# ---------------------------------------------------------------------------

from datetime import datetime, timezone, timedelta


def _loop_with_end(minutes_from_now: float, agenda=None, mcp=None) -> RealTimeLoop:
    """Build a loop whose scheduled end is `minutes_from_now` minutes in the future."""
    end = (datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)).isoformat()
    return RealTimeLoop(
        meeting_id="mtg-rt-001",
        record=_record(),
        mcp=mcp or _mcp(),
        cfg=_cfg(time_remaining_alert_minutes=5),
        agenda=agenda if agenda is not None else ["Budget review", "Roadmap"],
        scheduled_end_time=end,
    )


@pytest.mark.anyio
async def test_time_remaining_alert_sent_within_window():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=3, mcp=mock_mcp)  # 3 min left < 5 min threshold
    await loop._check_time_remaining()
    mock_mcp.send_realtime_alert.assert_awaited_once()
    alert_type = mock_mcp.send_realtime_alert.call_args.args[1]
    assert alert_type == "time_remaining"


@pytest.mark.anyio
async def test_time_remaining_alert_not_sent_outside_window():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=20, mcp=mock_mcp)  # 20 min left > 5 min threshold
    await loop._check_time_remaining()
    mock_mcp.send_realtime_alert.assert_not_awaited()


@pytest.mark.anyio
async def test_time_remaining_alert_fires_only_once():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=3, mcp=mock_mcp)
    await loop._check_time_remaining()
    await loop._check_time_remaining()  # second call — already sent
    assert mock_mcp.send_realtime_alert.await_count == 1


@pytest.mark.anyio
async def test_time_remaining_alert_not_sent_when_no_end_time():
    mock_mcp = _mcp()
    loop = RealTimeLoop(
        meeting_id="mtg-rt-001",
        record=_record(),
        mcp=mock_mcp,
        cfg=_cfg(time_remaining_alert_minutes=5),
        agenda=["Budget review"],
        scheduled_end_time=None,
    )
    await loop._check_time_remaining()
    mock_mcp.send_realtime_alert.assert_not_awaited()


@pytest.mark.anyio
async def test_time_remaining_card_includes_uncovered_topics():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=3, mcp=mock_mcp,
                          agenda=["Budget review", "Roadmap"])
    # Simulate that "Budget review" was covered but "Roadmap" was not
    loop._topic_max_scores = {"Budget review": 0.9, "Roadmap": 0.1}
    await loop._check_time_remaining()

    card = mock_mcp.send_realtime_alert.call_args.args[2]
    assert "Roadmap" in card["uncovered_agenda_topics"]
    assert "Budget review" not in card["uncovered_agenda_topics"]


@pytest.mark.anyio
async def test_time_remaining_card_empty_uncovered_when_all_covered():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=3, mcp=mock_mcp,
                          agenda=["Budget review", "Roadmap"])
    loop._topic_max_scores = {"Budget review": 0.9, "Roadmap": 0.8}
    await loop._check_time_remaining()

    card = mock_mcp.send_realtime_alert.call_args.args[2]
    assert card["uncovered_agenda_topics"] == []


@pytest.mark.anyio
async def test_time_remaining_card_includes_minutes_remaining():
    mock_mcp = _mcp()
    loop = _loop_with_end(minutes_from_now=4, mcp=mock_mcp)
    await loop._check_time_remaining()

    card = mock_mcp.send_realtime_alert.call_args.args[2]
    assert card["minutes_remaining"] >= 3  # allow for test execution time
