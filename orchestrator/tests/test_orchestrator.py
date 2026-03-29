"""Tests for Orchestrator lifecycle coordination."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import OrchestratorConfig
from orchestrator import Orchestrator


def _config() -> OrchestratorConfig:
    return OrchestratorConfig(
        transcript_capture_interval_seconds=1,
        specialist_agent_timeout_seconds=5,
    )


def _make_mcp() -> MagicMock:
    mcp = MagicMock()
    mcp.get_calendar_event = AsyncMock()
    mcp.store_meeting_record = AsyncMock()
    mcp.send_realtime_alert = AsyncMock()
    mcp.store_analysis_report = AsyncMock()
    mcp.post_adaptive_card = AsyncMock()
    return mcp


def _make_orchestrator(mcp=None) -> Orchestrator:
    """Build an Orchestrator with all external dependencies mocked."""
    cfg = _config()
    mcp = mcp or _make_mcp()

    with (
        patch("orchestrator.build_foundry_client") as mock_foundry,
        patch("orchestrator.load_agent_ids", return_value={
            "transcript": "t-id", "analysis": "a-id", "sentiment": "s-id"
        }),
    ):
        mock_foundry.return_value = MagicMock()
        orch = Orchestrator(config=cfg, mcp=mcp)

    return orch


# ------------------------------------------------------------------
# on_meeting_start
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_on_meeting_start_calls_initiator():
    orch = _make_orchestrator()
    mock_record = MagicMock()
    orch._initiator.initialise = AsyncMock(return_value=mock_record)
    orch._start_loops = MagicMock()

    await orch.on_meeting_start("mtg-001", [{"id": "p-1"}])

    orch._initiator.initialise.assert_awaited_once_with("mtg-001", [{"id": "p-1"}])
    orch._start_loops.assert_called_once_with("mtg-001", mock_record)


@pytest.mark.anyio
async def test_on_meeting_start_starts_loops():
    orch = _make_orchestrator()
    orch._initiator.initialise = AsyncMock(return_value=MagicMock())

    started_tasks = []

    def capture_start(meeting_id, record):
        started_tasks.append(meeting_id)

    orch._start_loops = capture_start

    await orch.on_meeting_start("mtg-001", [])
    assert "mtg-001" in started_tasks


# ------------------------------------------------------------------
# on_meeting_end
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_on_meeting_end_cancels_loops_then_runs_analyzer():
    orch = _make_orchestrator()
    call_order = []

    async def mock_cancel():
        call_order.append("cancel")

    async def mock_run(meeting_id):
        call_order.append("analyze")

    orch._cancel_loops = mock_cancel
    orch._post_analyzer.run = mock_run

    await orch.on_meeting_end("mtg-001")

    assert call_order == ["cancel", "analyze"]


@pytest.mark.anyio
async def test_on_meeting_end_passes_meeting_id_to_analyzer():
    orch = _make_orchestrator()
    orch._cancel_loops = AsyncMock()
    orch._post_analyzer.run = AsyncMock()

    await orch.on_meeting_end("mtg-special")

    orch._post_analyzer.run.assert_awaited_once_with("mtg-special")


# ------------------------------------------------------------------
# _cancel_loops
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_cancel_loops_cancels_running_tasks():
    orch = _make_orchestrator()

    async def never_ending():
        await asyncio.sleep(9999)

    orch._capture_task = asyncio.create_task(never_ending())
    orch._realtime_task = asyncio.create_task(never_ending())

    await orch._cancel_loops()

    assert orch._capture_task.cancelled()
    assert orch._realtime_task.cancelled()


@pytest.mark.anyio
async def test_cancel_loops_handles_none_tasks_gracefully():
    orch = _make_orchestrator()
    orch._capture_task = None
    orch._realtime_task = None
    # Should not raise
    await orch._cancel_loops()


@pytest.mark.anyio
async def test_cancel_loops_skips_already_done_tasks():
    orch = _make_orchestrator()

    async def quick():
        pass

    task = asyncio.create_task(quick())
    await task  # let it finish
    orch._capture_task = task
    orch._realtime_task = None

    # Should not raise even though task is already done
    await orch._cancel_loops()


# ------------------------------------------------------------------
# _capture_segment
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_capture_segment_dispatches_correct_task():
    orch = _make_orchestrator()
    orch._foundry.dispatch = AsyncMock(return_value={"gap_detected": False})

    await orch._capture_segment("mtg-001", 60)

    call_args = orch._foundry.dispatch.call_args
    agent_id, task = call_args[0]
    assert agent_id == "t-id"
    assert task["task"] == "capture_transcript_segment"
    assert task["meeting_id"] == "mtg-001"
    assert task["segment_window_seconds"] == 60


@pytest.mark.anyio
async def test_capture_segment_logs_gap_detected(caplog):
    import logging
    orch = _make_orchestrator()
    orch._foundry.dispatch = AsyncMock(return_value={"gap_detected": True})

    with caplog.at_level(logging.WARNING, logger="orchestrator"):
        await orch._capture_segment("mtg-001", 60)

    assert "gap" in caplog.text.lower()
