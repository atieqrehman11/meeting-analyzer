# Local Testing Guide

This guide covers how to run the Meeting Analyzer stack locally and test it end-to-end using Postman or Bruno without any Azure dependencies.

## Prerequisites

- Python 3.11+
- `.venv` created and packages installed
- `.env` configured

## Setup

**1. Install packages**

```bash
./run-dev.sh install
```

**2. Initialise `.env`**

```bash
./run-dev.sh env:init
```

**3. Start all services**

```bash
./run-dev.sh all
```

| Service | URL |
|---------|-----|
| MCP server | http://localhost:8000 |
| MCP Swagger UI | http://localhost:8000/docs |
| Teams Bot | http://localhost:3978 |
| Bot Swagger UI | http://localhost:3978/docs |

---

## Foundry Mode — Choosing Your Agent Backend

The orchestrator dispatches tasks to specialist agents (transcript, analysis, sentiment) after a meeting ends. Locally, Azure AI Foundry is not available, so two alternatives are provided via `ORCH_FOUNDRY_MODE` in `.env`.

### Mode 1: Mock (default)

```env
ORCH_FOUNDRY_MODE=mock
```

Returns hardcoded canned responses for every agent task. No external calls, no API key needed. Good for testing the plumbing — verifying the lifecycle flow, MCP storage, and report compilation work end-to-end.

What you get in the analysis report:
- Agenda: `["Mock agenda item 1", "Mock agenda item 2"]`
- Empty adherence, participation, and action items
- Status: `ok`

### Mode 2: Local OpenAI agents

```env
ORCH_FOUNDRY_MODE=local
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Runs real agent logic using OpenAI chat completions. Each agent receives the actual task payload and produces a response that matches the A2A schema contracts. This is the closest you can get to production behaviour without Azure AI Foundry.

What you get in the analysis report:
- Inferred agenda topics extracted from the meeting context
- Agenda adherence scores per topic
- Action items with owners and due dates extracted from the transcript
- Participation summary with sentiment per participant
- Realistic time allocation breakdown

`gpt-4o-mini` is recommended for local dev — it's fast and cheap. Switch to `gpt-4o` for higher quality output.

---

## How the Local Agents Work

The local agents live in `local_agents/` and implement the same task/response contracts as the Azure AI Foundry agents defined in `agents/instructions/`.

```
local_agents/
  base.py              OpenAI wrapper — sends system prompt + task JSON, parses JSON response
  transcript_agent.py  Handles: capture_transcript_segment, finalize_transcript
  analysis_agent.py    Handles: analyze_meeting
  sentiment_agent.py   Handles: analyze_sentiment, compute_participation_pulse
  dispatcher.py        Routes by task type, wraps calls as async
```

### Flow when a meeting ends

```
Bot receives "members removed" event
  → Orchestrator.on_meeting_end()
    → PostMeetingAnalyzer.run()
      → foundry.dispatch("agent-transcript", FinalizeTranscriptTask)
          → LocalFoundryClient → TranscriptAgent → OpenAI → JSON response
      → foundry.dispatch_with_timeout("agent-analysis", AnalyzeMeetingTask)   ┐ parallel
      → foundry.dispatch_with_timeout("agent-sentiment", AnalyzeSentimentTask) ┘
          → LocalFoundryClient → AnalysisAgent / SentimentAgent → OpenAI → JSON response
      → compile_report(analysis_response, sentiment_response)
      → mcp.store_analysis_report(report)
```

### What each agent receives and returns

**TranscriptAgent** — `finalize_transcript`

Input:
```json
{ "task": "finalize_transcript", "meeting_id": "mtg-001" }
```
Output:
```json
{
  "task": "finalize_transcript",
  "status": "ok",
  "transcript_blob_url": "mock://transcripts/mtg-001/final.json"
}
```

**AnalysisAgent** — `analyze_meeting`

Input:
```json
{
  "task": "analyze_meeting",
  "meeting_id": "mtg-001",
  "transcript_blob_url": "mock://transcripts/mtg-001/final.json",
  "agenda": []
}
```
Output (example with real OpenAI):
```json
{
  "task": "analyze_meeting",
  "status": "ok",
  "agenda": ["Q3 Feature Prioritisation", "Technical Feasibility Review", "Design and UX Alignment"],
  "agenda_source": "inferred",
  "agenda_adherence": [
    { "topic": "Q3 Feature Prioritisation", "status": "Covered", "similarity_score": 0.87, "time_minutes": 18.0, "time_percentage": 30.0 }
  ],
  "action_items": [
    { "description": "Define minimum viable offline scope", "owner_participant_id": "james-eng", "owner_name": "James Okafor", "due_date": "2026-07-18", "transcript_timestamp": "2026-07-15T09:08:00Z", "status": "Confirmed" }
  ],
  "sections_failed": []
}
```

**SentimentAgent** — `analyze_sentiment`

Input:
```json
{
  "task": "analyze_sentiment",
  "meeting_id": "mtg-001",
  "transcript_blob_url": "mock://transcripts/mtg-001/final.json"
}
```
Output (example with real OpenAI):
```json
{
  "task": "analyze_sentiment",
  "status": "ok",
  "participation_summary": [
    { "participant_id": "sarah-pm", "speaking_time_seconds": 420.0, "speaking_time_percentage": 45.0, "turn_count": 10, "participation_flag": null, "sentiment": "Positive" },
    { "participant_id": "james-eng", "speaking_time_seconds": 310.0, "speaking_time_percentage": 33.0, "turn_count": 8, "participation_flag": null, "sentiment": "Neutral" }
  ],
  "sections_failed": []
}
```

### Limitations of local agents vs production

| Capability | Local (OpenAI) | Production (Azure Foundry) |
|------------|---------------|---------------------------|
| Agenda inference | ✓ from task context | ✓ from actual transcript blob |
| Action item extraction | ✓ from task context | ✓ from full transcript text |
| Sentiment analysis | ✓ simulated | ✓ Azure AI Language API |
| Transcript capture | Simulated (no Graph API) | Real Graph Communications API |
| Prosody features | Not available | Azure AI Speech batch API |
| Blob storage | mock:// URLs | Real Azure Blob Storage |

The key difference: locally the agents don't have access to the actual stored transcript text (that would require reading from blob storage). They infer responses from the task metadata. For richer local analysis, use the **Realistic Demo collection** which stores 29 real transcript segments before triggering the analysis — the agents receive the meeting context and produce more meaningful output.

---

## API Collections

| Collection | Purpose |
|------------|---------|
| `postman/Meeting Analyzer.postman_collection.json` | Basic lifecycle, one request per endpoint, error contract tests |
| `postman/Meeting Analyzer - Realistic Demo.postman_collection.json` | Full Q3 roadmap meeting scenario, 43 requests, real transcript |

Generate the realistic demo collection (regenerate after changing the scenario):
```bash
python postman/generate_demo_collection.py
```

---

## Test Sequence (Basic Collection)

### Phase 1 — Start the meeting

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 1 | Teams Bot | Bot Joins Meeting | `201` |

### Phase 2 — Verify meeting initialised

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 2 | MCP - Meeting | Get Calendar Event | `200` |
| 3 | MCP - Meeting | Get Recording Status | `200` |

### Phase 3 — Consent

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 4 | MCP - Consent | Store Consent - Granted | `204` |
| 5 | MCP - Consent | Store Consent - Declined | `204` |

### Phase 4 — Transcript

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 6 | MCP - Transcript | Store Segment - Consented | `204` |
| 7 | MCP - Transcript | Store Segment - No Consent | `400 CONSENT_REQUIRED` |

### Phase 5 — Realtime monitoring

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 8 | MCP - Similarity | Compute Similarity | `200` with scores |
| 9 | MCP - Realtime | Get Participant Rates | `200` |
| 10 | MCP - Realtime | Store Cost Snapshot | `204` |
| 11 | MCP - Realtime | Send Alert - Off Track | `204` |
| 12 | MCP - Realtime | Send Alert - Unknown Type | `400 FEATURE_NOT_ENABLED` |

### Phase 6 — End the meeting

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 13 | Teams Bot | Bot Leaves Meeting | `201` |

Triggers `PostMeetingAnalyzer` → agents → `AnalysisReport` stored in MCP.

### Phase 7 — Verify post-meeting output

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 14 | MCP - Analysis | Get Analysis Report | `200` with report |
| 15 | MCP - Analysis | Get Report - Not Found | `400 REPORT_NOT_FOUND` |

### Phase 8 — Poll

| # | Folder | Request | Expected |
|---|--------|---------|----------|
| 16 | MCP - Poll | Create Poll | `200` with `poll_id` |

---

## Error Responses

All MCP errors follow this envelope:

```json
{
  "error": {
    "code": "REPORT_NOT_FOUND",
    "message": "No report found for meeting 'mtg-001'.",
    "retryable": false
  }
}
```

| Code | Trigger |
|------|---------|
| `CONSENT_REQUIRED` | Transcript segment with `consent_verified: false` |
| `REPORT_NOT_FOUND` | `get_analysis_report` before report is stored |
| `FEATURE_NOT_ENABLED` | `send_realtime_alert` with unrecognised alert type |

---

## Notes

- The mock backend is **in-memory** — all data resets on MCP server restart
- `store_*` endpoints return `204 No Content` — no body is correct behaviour
- Similarity scores use hash-based embeddings locally — no embedding model needed
- The bot skips Teams auth validation when `BOT_APP_ID` / `BOT_APP_PASSWORD` are empty
- To switch to Azure: set `MCP_BACKEND_MODE=azure`, `ORCH_FOUNDRY_MODE=azure`, and fill in Azure credentials in `.env`
