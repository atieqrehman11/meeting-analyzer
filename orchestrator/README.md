# orchestrator — Component Architecture

This document describes how the components inside `orchestrator` connect with each other.

---

## Directory Overview

```
orchestrator/
├── orchestrator.py          # Top-level lifecycle coordinator (one instance per meeting)
├── meeting_initiator.py     # Setup on meeting join — fetches calendar, persists record
├── real_time_loop.py        # Background evaluation loop running during the meeting
├── post_meeting_analyzer.py # Post-meeting pipeline — transcript, analysis, sentiment
├── report_builder.py        # Pure functions: compile report + build Adaptive Card
├── foundry_client.py        # A2A dispatch to Azure AI Foundry agents (or mock/local)
├── mcp_client.py            # Typed HTTP client for all MCP server tools
├── config.py                # All config via env vars (ORCH_ prefix)
└── agent_ids.json           # Maps agent role → Azure AI Foundry agent ID
```

---

## Component Connections

```
                    ┌──────────────────────────────────────────────────┐
                    │                  Orchestrator                     │
                    │               orchestrator.py                    │
                    │  (one instance per active meeting)               │
                    └───┬──────────────┬──────────────────┬────────────┘
                        │              │                  │
              creates   │    creates   │        creates   │
         ┌──────────────▼──┐  ┌────────▼──────┐  ┌───────▼────────────┐
         │ MeetingInitiator│  │  RealTimeLoop │  │PostMeetingAnalyzer │
         │ (on start)      │  │  (background) │  │ (on end)           │
         └──────────────┬──┘  └────────┬──────┘  └───────┬────────────┘
                        │              │                  │
                        └──────┬───────┘                  │
                               │ MCP calls                │ MCP + Foundry calls
                    ┌──────────▼──────────┐    ┌──────────▼──────────┐
                    │     McpClient       │    │    FoundryClient     │
                    │   mcp_client.py     │    │  foundry_client.py  │
                    └──────────┬──────────┘    └──────────┬──────────┘
                               │ HTTP POST                │ A2A dispatch
                    ┌──────────▼──────────┐    ┌──────────▼──────────┐
                    │     MCP Server      │    │  Azure AI Foundry   │
                    │  (external service) │    │  (or mock/local)    │
                    └─────────────────────┘    └─────────────────────┘
```

---

## Orchestrator (`orchestrator.py`)

The `Orchestrator` is the single owner of a meeting's lifecycle. The bot creates one instance per active meeting via `orchestrator_factory.py`.

On construction it builds:
- `MeetingInitiator` — injected with `McpClient`
- `PostMeetingAnalyzer` — injected with `FoundryClient`, `McpClient`, and `agent_ids`
- `FoundryClient` — constructed via `build_foundry_client(config)` based on `ORCH_FOUNDRY_MODE`

On `on_meeting_start()`:
1. Delegates setup to `MeetingInitiator.initialise()`
2. Starts two asyncio background tasks: transcript capture loop and `RealTimeLoop`

On `on_meeting_end()`:
1. Cancels both background tasks
2. Delegates post-meeting work to `PostMeetingAnalyzer.run()`

---

## Meeting Initiator (`meeting_initiator.py`)

Runs once when the meeting starts.

```
MeetingInitiator.initialise(meeting_id, roster)
  ├─ mcp.get_calendar_event()       → CalendarEventOutput
  ├─ mcp.send_realtime_alert()      → "missing_agenda" alert (if no agenda found)
  ├─ _build_meeting_record()        → MeetingRecord  (pure, no I/O)
  └─ mcp.store_meeting_record()     → persists to MCP
```

Returns the `MeetingRecord` which is passed to `RealTimeLoop` for state tracking.

---

## Real-Time Loop (`real_time_loop.py`)

Runs as a background asyncio task for the duration of the meeting. Waits for `realtime_loop_start_delay_seconds` before the first tick, then fires every `realtime_loop_interval_seconds`.

Each tick runs five checks in sequence:

| Check | What it does | Alert sent |
|-------|-------------|------------|
| Agenda adherence | Calls `mcp.compute_similarity()`, buffers scores, checks consecutive windows | `off_track`, `agenda_unclear`, `agenda_unclear_second` |
| Purpose detection | Detects meeting purpose after a delay, re-checks for drift | `purpose_detected`, `purpose_drift` |
| Tone monitoring | Stub — real impl would call LLM with recent transcript | `tone_meeting`, `tone_private` |
| Participation pulse | Calls `mcp.get_participant_rates()`, snapshots active/silent speakers | `silent_participant` |
| Time remaining | Fires once when within `time_remaining_alert_minutes` of scheduled end | `time_remaining` |

All alerts go through `_send_throttled_alert()` which suppresses repeats within `alert_throttle_window_seconds`, except `time_remaining` which fires exactly once.

---

## Post-Meeting Analyzer (`post_meeting_analyzer.py`)

Runs once when the meeting ends. Executes a three-stage pipeline:

```
PostMeetingAnalyzer.run(meeting_id)
  │
  ├─ 1. _finalise_transcript()
  │      └─ foundry.dispatch(transcript_agent, FinalizeTranscriptTask)
  │           → transcript_blob_url
  │
  ├─ 2. _analyse()  [parallel via asyncio.gather]
  │      ├─ foundry.dispatch_with_timeout(analysis_agent, AnalyzeMeetingTask)
  │      │    → AnalyzeMeetingResponse
  │      └─ foundry.dispatch_with_timeout(sentiment_agent, AnalyzeSentimentTask)
  │           → AnalyzeSentimentResponse
  │
  └─ 3. _deliver()
         ├─ report_builder.compile_report()   → AnalysisReport  (pure)
         ├─ mcp.store_analysis_report()
         └─ mcp.post_adaptive_card()
              └─ on failure: fallback DM via mcp.post_adaptive_card()
```

Analysis and sentiment agents run in parallel. If either fails or times out, the report is still compiled with a `sections_unavailable` entry for the failed section.

---

## Report Builder (`report_builder.py`)

Pure functions with no I/O — fully unit-testable in isolation.

- `compile_report(meeting_id, analysis, sentiment)` — merges both agent responses into an `AnalysisReport`, gracefully handling `BaseException` from either
- `build_report_card(report)` — converts an `AnalysisReport` into an Adaptive Card dict ready to POST

---

## Foundry Client (`foundry_client.py`)

Wraps Azure AI Foundry's `AgentsClient` for A2A task dispatch. The concrete implementation is chosen at startup by `build_foundry_client(config)` based on `ORCH_FOUNDRY_MODE`:

| Mode | Class | Used for |
|------|-------|---------|
| `mock` | `MockFoundryClient` | Local dev — returns canned responses, no external calls |
| `local` | `LocalFoundryClient` (from `local_agents`) | Local dev with real OpenAI API |
| `azure` | `FoundryClient` | Production — calls Azure AI Foundry |

`FoundryClient.dispatch_with_timeout()` retries once on timeout before returning an error dict.

Agent IDs are loaded from `agent_ids.json` at startup via `load_agent_ids()`. The JSON keys must match what the code expects:

```json
{
  "transcript": "<agent-id>",
  "analysis":   "<agent-id>",
  "sentiment":  "<agent-id>"
}
```

> Note: `deploy/register_agents.py` generates this file after deploying agents to Foundry. If the file is missing, the orchestrator will raise `FileNotFoundError` on startup.

---

## MCP Client (`mcp_client.py`)

Typed async HTTP client for all MCP server tools. Extends `BaseMcpClient` from `shared_models`.

Organised by MCP tool group:

| Group | Methods |
|-------|---------|
| Meeting | `get_calendar_event`, `get_recording_status`, `store_meeting_record`, `post_adaptive_card` |
| Transcript | `store_transcript_segment` |
| Consent | `store_consent_record` |
| Analysis | `store_analysis_report`, `get_analysis_report` |
| Similarity | `compute_similarity` |
| Real-time | `send_realtime_alert`, `get_participant_rates`, `store_cost_snapshot` |
| Poll | `create_poll` |

Retries retryable errors up to `mcp_retry_max_attempts` times with configurable backoff. Non-retryable errors raise `McpCallError` immediately.

---

## Configuration (`config.py`)

All settings loaded from environment variables with the `ORCH_` prefix.

| Env var | Default | Purpose |
|---------|---------|---------|
| `ORCH_FOUNDRY_MODE` | `azure` | `azure` / `local` / `mock` |
| `ORCH_AZURE_AI_PROJECT_ENDPOINT` | — | Azure AI Foundry project endpoint |
| `ORCH_MCP_SERVER_URL` | `http://localhost:8000` | MCP server base URL |
| `ORCH_TRANSCRIPT_CAPTURE_INTERVAL_SECONDS` | `60` | How often to capture a transcript segment |
| `ORCH_REALTIME_LOOP_INTERVAL_SECONDS` | `60` | Tick interval for the real-time loop |
| `ORCH_REALTIME_LOOP_START_DELAY_SECONDS` | `120` | Delay before first real-time tick |
| `ORCH_OFF_TRACK_CONSECUTIVE_WINDOWS` | `3` | Windows below threshold before off-track alert |
| `ORCH_OFF_TRACK_SIMILARITY_THRESHOLD` | `0.35` | Similarity score below which discussion is off-track |
| `ORCH_ALERT_THROTTLE_WINDOW_SECONDS` | `300` | Minimum gap between repeated alerts of the same type |
| `ORCH_SPECIALIST_AGENT_TIMEOUT_SECONDS` | `120` | Per-agent timeout for post-meeting dispatch |
| `ORCH_SILENT_PARTICIPANT_THRESHOLD_MINUTES` | `10` | Minutes of silence before alerting |
| `ORCH_TIME_REMAINING_ALERT_MINUTES` | `5` | Minutes before end to send wrap-up alert |

---

## Meeting Lifecycle — Full Flow

```
Bot: on_meeting_start(meeting_id, roster)
  └─ Orchestrator.on_meeting_start()
       ├─ MeetingInitiator.initialise()     → MeetingRecord
       ├─ asyncio.create_task(transcript_capture_loop)
       └─ asyncio.create_task(RealTimeLoop.run())

         [meeting in progress]
         transcript_capture_loop  →  every 60s  →  foundry.dispatch(transcript_agent)
         RealTimeLoop._tick()     →  every 60s  →  mcp.compute_similarity()
                                                    mcp.get_participant_rates()
                                                    mcp.send_realtime_alert()  (throttled)

Bot: on_meeting_end(meeting_id)
  └─ Orchestrator.on_meeting_end()
       ├─ cancel transcript_capture_loop
       ├─ cancel RealTimeLoop
       └─ PostMeetingAnalyzer.run()
            ├─ foundry → transcript_agent   → transcript_blob_url
            ├─ foundry → analysis_agent  ┐  (parallel)
            ├─ foundry → sentiment_agent ┘
            ├─ compile_report()
            ├─ mcp.store_analysis_report()
            └─ mcp.post_adaptive_card()
```
