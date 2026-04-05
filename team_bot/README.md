# team_bot — Component Architecture

This document describes how the components inside `team_bot` connect with each other.

---

## Directory Overview

```
team_bot/
├── main.py                    # FastAPI app + lifespan (startup/shutdown)
├── bot.py                     # Bot Framework activity handler + meeting manager
├── graph_service.py           # Microsoft Graph subscription + proactive join
├── orchestrator_factory.py    # Wires Orchestrator + MCP client per meeting
├── mcp_client.py              # HTTP client for the MCP server
└── app/
    ├── config/settings.py     # All config via env vars (BOT_ prefix)
    ├── common/logger.py
    └── api/v1/
        ├── router.py          # Mounts teams.py router
        └── teams.py           # HTTP endpoints + adapter/manager singletons
```

---

## Component Connections

```
                        ┌─────────────────────────────────────────────────┐
                        │                   main.py                        │
                        │  FastAPI app, lifespan, includes API router      │
                        └────────┬──────────────────────┬──────────────────┘
                                 │ creates               │ creates
                    ┌────────────▼──────────┐   ┌───────▼──────────────────┐
                    │   GraphSubscription   │   │   API Router              │
                    │   Service             │   │   (app/api/v1/teams.py)   │
                    │   graph_service.py    │   │                           │
                    └────────────┬──────────┘   └───────┬──────────────────┘
                                 │ proactive join        │ process_activity
                    ┌────────────▼──────────────────────▼──────────────────┐
                    │              BotFrameworkAdapter                      │
                    │              (shared singleton in teams.py)           │
                    └───────────────────────────┬───────────────────────────┘
                                                │ on_turn
                    ┌───────────────────────────▼───────────────────────────┐
                    │                    TeamsMeetingBot                     │
                    │                       bot.py                          │
                    └───────────────────────────┬───────────────────────────┘
                                                │ start/end meeting
                    ┌───────────────────────────▼───────────────────────────┐
                    │              MeetingOrchestratorManager                │
                    │                       bot.py                          │
                    └───────────────────────────┬───────────────────────────┘
                                                │ build_meeting_orchestrator()
                    ┌───────────────────────────▼───────────────────────────┐
                    │              orchestrator_factory.py                   │
                    │   creates Orchestrator + TeamBotMcpClient per meeting  │
                    └──────────────┬────────────────────────────────────────┘
                                   │ HTTP POST
                    ┌──────────────▼────────────────────────────────────────┐
                    │              TeamBotMcpClient                          │
                    │              mcp_client.py  →  MCP Server             │
                    └───────────────────────────────────────────────────────┘
```

---

## Startup Sequence (`main.py` lifespan)

1. `GraphSubscriptionService` is created with credentials from `settings`
2. `subscribe()` registers a Graph change notification for online meeting events
3. `start_renewal_loop()` starts a background task that renews the subscription every 50 min (Graph max is 60 min)
4. FastAPI begins serving requests

On shutdown, `manager.shutdown()` ends all active meetings and `graph_service.close()` cancels the renewal task.

---

## Singletons in `teams.py`

`teams.py` owns three module-level singletons that are shared across the request lifecycle:

| Singleton | Type | Used by |
|-----------|------|---------|
| `adapter` | `BotFrameworkAdapter` | `POST /api/messages`, `graph_service.proactive_join()` |
| `manager` | `MeetingOrchestratorManager` | `TeamsMeetingBot` |
| `bot` | `TeamsMeetingBot` | `POST /api/messages` |

`main.py` imports `manager` and `adapter` from `teams.py` to pass into `GraphSubscriptionService`, avoiding circular imports by lazily importing `graph_service` inside the webhook handler.

---

## HTTP Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/messages` | Main Bot Framework endpoint — receives all Teams activity events |
| `GET` | `/api/graph/webhook` | Graph subscription validation handshake (echoes `validationToken`) |
| `POST` | `/api/graph/webhook` | Graph change notification — triggers proactive bot join |

---

## Two Paths to Meeting Start

### 1. Proactive join (via Graph webhook)
```
Graph API
  → POST /api/graph/webhook
  → validate clientState secret
  → graph_service.proactive_join()
  → adapter.continue_conversation()
  → Teams sends conversationUpdate/membersAdded back
  → bot.on_conversation_update_activity()
  → manager.start_meeting()
```

### 2. Manual add (user adds bot in meeting)
```
Teams
  → POST /api/messages  (conversationUpdate, membersAdded)
  → adapter.process_activity()
  → bot.on_conversation_update_activity()
  → manager.start_meeting()
```

Both paths converge at `manager.start_meeting()`.

---

## Meeting Lifecycle

```
manager.start_meeting(meeting_id, roster)
  └─ orchestrator_factory.build_meeting_orchestrator()
       ├─ creates TeamBotMcpClient(base_url, retries, backoff)
       ├─ creates Orchestrator(config, mcp_client)
       └─ stores (orchestrator, mcp_client) in _active_meetings[meeting_id]
  └─ orchestrator.on_meeting_start(meeting_id, roster)

manager.end_meeting(meeting_id)
  └─ orchestrator.on_meeting_end(meeting_id)
  └─ mcp_client.aclose()
```

Each active meeting gets its own `Orchestrator` + `TeamBotMcpClient` pair. The client is closed when the meeting ends.

---

## Configuration (`app/config/settings.py`)

All settings are loaded from environment variables with the `BOT_` prefix.

| Env var | Default | Purpose |
|---------|---------|---------|
| `BOT_APP_DISPLAY_NAME` | `Meeting Assistant` | Display name shown in Teams messages and cards |
| `BOT_APP_ID` | — | Azure AD app registration client ID |
| `BOT_APP_PASSWORD` | — | Azure AD app registration client secret |
| `BOT_MCP_SERVER_URL` | `http://localhost:8000` | MCP server base URL |
| `BOT_MCP_RETRY_MAX_ATTEMPTS` | `3` | Retry attempts for MCP calls |
| `BOT_MCP_RETRY_BACKOFF_SECONDS` | `[1, 2, 4]` | Backoff intervals between retries |
| `BOT_GRAPH_TENANT_ID` | — | Azure AD tenant for Graph API |
| `BOT_GRAPH_CLIENT_ID` | — | App client ID for Graph API |
| `BOT_GRAPH_CLIENT_SECRET` | — | App secret for Graph API |
| `BOT_WEBHOOK_BASE_URL` | — | Public HTTPS URL of this service (used to register Graph subscription) |
| `BOT_WEBHOOK_SECRET` | `change-me-in-production` | Shared secret to validate Graph notifications |

If `BOT_WEBHOOK_BASE_URL` is empty, the Graph subscription is skipped and the bot can only join when manually added to a meeting.
