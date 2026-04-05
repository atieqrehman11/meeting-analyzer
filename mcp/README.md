# mcp — Component Architecture

This document describes how the components inside `mcp` connect with each other.

---

## Directory Overview

```
mcp/
├── main.py                        # FastAPI app + lifespan (backend wiring)
└── app/
    ├── dependencies.py            # FastAPI dependency resolvers (backend accessors)
    ├── config/settings.py         # All config via env vars (MCP_ prefix)
    ├── common/
    │   ├── exceptions.py          # Domain exceptions + error envelope + handlers
    │   └── logger.py
    ├── api/v1/
    │   ├── router.py              # Mounts all tool routers under /v1/tools
    │   └── tools/
    │       ├── meeting.py         # get_calendar_event, get_recording_status, store_meeting_record, post_adaptive_card
    │       ├── transcript.py      # store_transcript_segment
    │       ├── consent.py         # store_consent_record
    │       ├── analysis.py        # store_analysis_report, get_analysis_report
    │       ├── similarity.py      # compute_similarity
    │       ├── realtime.py        # send_realtime_alert, get_participant_rates, store_cost_snapshot
    │       └── poll.py            # create_poll
    └── services/
        ├── similarity.py          # In-process cosine similarity with embedding cache
        └── backends/
            ├── base.py            # Abstract interfaces: StorageBackend, DatabaseBackend, GraphBackend
            ├── mock.py            # In-memory implementations (local dev, no Azure)
            ├── graph.py           # Real Microsoft Graph API implementation
            └── cards.py           # Adaptive Card renderers for all alert types
```

---

## Component Connections

```
                         ┌─────────────────────────────────────┐
                         │              main.py                │
                         │  FastAPI app, lifespan, backends    │
                         └──────────────┬──────────────────────┘
                                        │ _build_backends()
                         ┌──────────────┼──────────────┐
                         │              │              │
              ┌──────────▼─────┐ ┌──────▼──────┐ ┌────▼────────────────┐
              │ StorageBackend │ │DatabaseBack │ │   GraphBackend      │
              │  (mock only)   │ │ (mock only) │ │ mock | AzureGraph   │
              └────────────────┘ └─────────────┘ └────────┬────────────┘
                                                           │ uses
                                                  ┌────────▼────────────┐
                                                  │      cards.py       │
                                                  │  (alert renderers)  │
                                                  └─────────────────────┘

                         ┌─────────────────────────────────────┐
                         │          dependencies.py             │
                         │  StorageDep / DatabaseDep /         │
                         │  GraphDep / SimilarityDep           │
                         └──────────────┬──────────────────────┘
                                        │ injected into
                         ┌──────────────▼──────────────────────┐
                         │     Tool endpoints (api/v1/tools/)  │
                         │  meeting  transcript  consent       │
                         │  analysis  similarity  realtime  poll│
                         └─────────────────────────────────────┘
```

---

## Startup (`main.py` lifespan)

`_build_backends()` runs once on startup and attaches backend instances to `app.state`:

| `app.state` key | `mock` mode | `azure` mode |
|-----------------|-------------|--------------|
| `storage` | `MockStorageBackend` | `MockStorageBackend` (Azure pending) |
| `db` | `MockDatabaseBackend` | `MockDatabaseBackend` (Azure pending) |
| `graph` | `MockGraphBackend` | `AzureGraphBackend` |
| `similarity` | `SimilarityService` | `SimilarityService` |

On shutdown, `AzureGraphBackend.close()` is called if present to release the HTTP client.

---

## Dependency Injection (`dependencies.py`)

Tool endpoints never access `app.state` directly. Instead they declare typed dependencies:

```python
StorageDep   → app.state.storage   (StorageBackend)
DatabaseDep  → app.state.db        (DatabaseBackend)
GraphDep     → app.state.graph     (GraphBackend)
SimilarityDep → app.state.similarity (SimilarityService)
```

Swapping `mock` → `azure` only requires changing what `_build_backends()` assigns — no tool code changes.

---

## Tool Endpoints

All routes are mounted under `/v1/tools` by `router.py`. Each tool file owns one prefix:

| Prefix | Tool | Backends used |
|--------|------|---------------|
| `/meeting` | `get_calendar_event` | `GraphDep` |
| `/meeting` | `get_recording_status` | `GraphDep` |
| `/meeting` | `store_meeting_record` | `DatabaseDep` |
| `/meeting` | `post_adaptive_card` | `GraphDep` |
| `/transcript` | `store_transcript_segment` | `DatabaseDep` |
| `/consent` | `store_consent_record` | `DatabaseDep` |
| `/analysis` | `store_analysis_report` | `DatabaseDep` |
| `/analysis` | `get_analysis_report` | `DatabaseDep` |
| `/similarity` | `compute_similarity` | `SimilarityDep` |
| `/realtime` | `send_realtime_alert` | `GraphDep` |
| `/realtime` | `get_participant_rates` | `DatabaseDep` |
| `/realtime` | `store_cost_snapshot` | `DatabaseDep` |
| `/poll` | `create_poll` | `GraphDep` |

Full path example: `POST /v1/tools/realtime/send_realtime_alert`

---

## Backend Implementations

### `base.py` — Abstract interfaces

Three abstract base classes define the contracts all tool code depends on:

- `StorageBackend` — blob read/write
- `DatabaseBackend` — upsert/get for meetings, consent, segments, reports, action items, cost snapshots, participant rates
- `GraphBackend` — Graph API operations: calendar events, recording status, adaptive cards, realtime alerts, polls

### `mock.py` — In-memory implementations

All state lives in process memory (plain dicts). No Azure credentials needed. Used for local dev and tests.

### `graph.py` — `AzureGraphBackend`

Real Microsoft Graph API calls using app-only (`client_credentials`) auth. Token is cached and refreshed automatically with a mutex to prevent concurrent refresh races.

Key internal flow for `send_realtime_alert`:
```
send_realtime_alert(meeting_id, alert_type, card_payload)
  ├─ cards.render_alert_card(alert_type, card_payload)  → Adaptive Card dict
  ├─ _get_meeting_chat_id(meeting_id)                   → Graph: chatInfo.threadId
  ├─ _wrap_card(rendered)                               → Graph chat message envelope
  └─ _post_chat_message(chat_id, body, token)           → POST /chats/{id}/messages
```

Required Graph application permissions:
- `OnlineMeetings.Read.All`
- `Calendars.Read`
- `OnlineMeetings.ReadWrite.All`
- `Chat.ReadWrite.All`

### `cards.py` — Adaptive Card renderers

Renders a typed Adaptive Card dict for each alert type. Called only by `AzureGraphBackend` (and `MockGraphBackend` logs instead of rendering).

Each alert type has a dedicated renderer registered via `@_register(...)`. Unknown types fall back to `_generic_card`. All cards share:
- `_header()` — coloured accent bar + icon + title
- `_footer()` — timestamp + `settings.app_display_name`

Registered alert types: `off_track`, `agenda_unclear`, `agenda_unclear_second`, `purpose_detected`, `purpose_drift`, `tone_meeting`, `tone_private`, `silent_participant`, `missing_agenda`, `time_remaining`

`build_poll_card()` is a separate entry point used by `create_poll`.

---

## Similarity Service (`services/similarity.py`)

In-process cosine similarity — no external service required. Agenda topic embeddings are computed once per meeting and cached by `meeting_id`.

Current embedding: deterministic unit vector derived from text hash (placeholder). Replace `_embed()` with an Azure OpenAI `text-embedding-3-small` call when available.

---

## Error Handling (`common/exceptions.py`)

All tool failures raise a subclass of `McpToolError`, which is caught by a registered FastAPI exception handler and returned as a structured JSON envelope:

```json
{ "error": { "code": "...", "message": "...", "retryable": false } }
```

| Exception | Code | HTTP |
|-----------|------|------|
| `McpToolError` (base) | any | 400 |
| `FeatureNotEnabledError` | `FEATURE_NOT_ENABLED` | 400 |
| `ValidationError` | `VALIDATION_ERROR` | 400 |
| `ConsentRequiredError` | `CONSENT_REQUIRED` | 400 |
| `RegionViolationError` | `REGION_VIOLATION` | 400 |
| unhandled `Exception` | `INTERNAL_ERROR` | 500 |

---

## Feature Flags

Two tools are gated by settings flags:

| Flag | Env var | Default | Effect when `False` |
|------|---------|---------|---------------------|
| Consent enforcement | `MCP_CONSENT_REQUIRED` | `false` | Transcript segments stored regardless of `consent_verified` |
| Poll delivery | `MCP_POLL_ENABLED` | `false` | `create_poll` raises `FEATURE_NOT_ENABLED` |

---

## Configuration (`config/settings.py`)

All settings loaded from environment variables with the `MCP_` prefix.

| Env var | Default | Purpose |
|---------|---------|---------|
| `MCP_APP_DISPLAY_NAME` | `Meeting Assistant` | Name shown in card footers and tone alerts |
| `MCP_BACKEND_MODE` | `mock` | `mock` or `azure` |
| `MCP_GRAPH_TENANT_ID` | — | Azure AD tenant (azure mode) |
| `MCP_GRAPH_CLIENT_ID` | — | App client ID (azure mode) |
| `MCP_GRAPH_CLIENT_SECRET` | — | App secret (azure mode) |
| `MCP_AZURE_STORAGE_ACCOUNT_URL` | — | Blob storage URL (azure mode, pending) |
| `MCP_COSMOS_ENDPOINT` | — | Cosmos DB endpoint (azure mode, pending) |
| `MCP_CONSENT_REQUIRED` | `false` | Enforce per-participant consent on transcript storage |
| `MCP_POLL_ENABLED` | `false` | Enable `create_poll` tool |
| `MCP_PORT` | `8000` | Server port |
| `MCP_LOG_LEVEL` | `INFO` | Log level |
