# Local Testing Guide

This guide covers how to run the Meeting Analyzer stack locally and test it end-to-end using Postman or Bruno without any Azure dependencies.

## Prerequisites

- Python 3.11+
- `.venv` created and packages installed
- `.env` configured

## Setup

**1. Install packages**

```bash
./manage.sh install
```

**2. Initialise `.env`**

```bash
./manage.sh env:init
```

Key values for local dev (already defaulted in `.env.example`):

```env
MCP_BACKEND_MODE=mock
ORCH_FOUNDRY_MODE=mock
ORCH_MCP_SERVER_URL=http://localhost:8000
```

`MCP_BACKEND_MODE=mock` uses in-memory storage — no Cosmos DB or Blob Storage needed.
`ORCH_FOUNDRY_MODE=mock` uses canned agent responses — no Azure AI Foundry needed.

**3. Start all services**

```bash
./manage.sh all
```

| Service | URL |
|---------|-----|
| MCP server | http://localhost:8000 |
| MCP Swagger UI | http://localhost:8000/docs |
| Teams Bot | http://localhost:3978 |
| Bot Swagger UI | http://localhost:3978/docs |

---

## Import the API Collection

- **Postman** — Import `postman/Meeting Analyzer.postman_collection.json`

Both collections use variables (`mcp_url`, `bot_url`, `meeting_id`, `bot_id`) that default to the local URLs above.

---

## Test Sequence

Run requests in this order to exercise the full meeting lifecycle.

### Phase 1 — Start the meeting

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 1 | Teams Bot | Bot Joins Meeting | `201 Created` |

This triggers `MeetingInitiator` which fetches the calendar event and stores the meeting record in MCP. Background loops start (transcript capture + realtime evaluation).

---

### Phase 2 — Verify meeting initialised

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 2 | MCP - Meeting | Get Calendar Event | `200` with mock agenda |
| 3 | MCP - Meeting | Get Recording Status | `200` with `recording_enabled: false` |

---

### Phase 3 — Consent

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 4 | MCP - Consent | Store Consent Record - Granted | `204 No Content` |
| 5 | MCP - Consent | Store Consent Record - Declined | `204 No Content` |

---

### Phase 4 — Transcript

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 6 | MCP - Transcript | Store Transcript Segment - Consented | `204 No Content` |
| 7 | MCP - Transcript | Store Transcript Segment - No Consent | `400 CONSENT_REQUIRED` |

Request 7 is an intentional error case — confirms the consent guard is working.

---

### Phase 5 — Realtime monitoring

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 8 | MCP - Similarity | Compute Similarity | `200` with per-topic scores |
| 9 | MCP - Realtime | Get Participant Rates | `200` with rate list |
| 10 | MCP - Realtime | Store Cost Snapshot | `204 No Content` |
| 11 | MCP - Realtime | Send Realtime Alert - Off Track | `204 No Content` |
| 12 | MCP - Realtime | Send Realtime Alert - Unknown Type | `400 FEATURE_NOT_ENABLED` |

Request 12 is an intentional error case — confirms the alert type guard is working.

---

### Phase 6 — End the meeting

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 13 | Teams Bot | Bot Leaves Meeting | `201 Created` |

This triggers `PostMeetingAnalyzer` which:
- Calls `MockFoundryClient` to finalise transcript, run analysis and sentiment in parallel
- Compiles an `AnalysisReport`
- Stores the report in MCP
- Posts an adaptive card summary

---

### Phase 7 — Verify post-meeting output

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
| 14 | MCP - Analysis | Get Analysis Report | `200` with compiled report |
| 15 | MCP - Analysis | Get Analysis Report - Not Found | `400 REPORT_NOT_FOUND` |

Request 15 is an intentional error case — confirms the error contract.

---

### Phase 8 — Poll (optional)

| # | Collection folder | Request | Expected |
|---|-------------------|---------|----------|
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
| `CONSENT_REQUIRED` | Transcript segment stored with `consent_verified: false` |
| `REPORT_NOT_FOUND` | `get_analysis_report` called before report is stored |
| `FEATURE_NOT_ENABLED` | `send_realtime_alert` called with an unrecognised alert type |

---

## Notes

- The mock backend is **in-memory** — all stored data resets on MCP server restart
- `store_*` endpoints always return `204 No Content` with no body — that is correct
- Similarity scores are non-zero random values derived from text hashes (no embedding model needed locally)
- The bot's `/api/messages` endpoint skips Teams auth token validation when `BOT_APP_ID` and `BOT_APP_PASSWORD` are empty in `.env`
- To switch to real Azure, set `MCP_BACKEND_MODE=azure` and `ORCH_FOUNDRY_MODE=azure` and fill in the Azure credentials in `.env`
