# Implementation Plan: Teams Meeting Analysis Bot

## Overview

Tasks are organized by work stream so team members can work in parallel. Within each stream, tasks are ordered by stage (1 → 2 → 3). All streams run in local dev mode through Stage 3 — no Azure infrastructure beyond AI Foundry models is needed until the Production Wiring section at the end.

**Work Streams:**
- A. Infrastructure & Dev Environment
- B. API Layer (MCP Server)
- C. Teams Integration (Bot Framework)
- D. AI Agents
- E. Production Wiring (deferred until after full MVP is validated locally)
- F. Phase 2 — Post-MVP

**Dev mode flags (default for all streams through Stage 3):**
- `STORAGE_BACKEND=local` — local filesystem + SQLite
- `AUTH_ENABLED=false` — no token validation
- `GRAPH_BACKEND=mock` — fixture JSON instead of real Graph API
- `BOT_MODE=simulate` — local script triggers meeting events

---

## A. Infrastructure & Dev Environment

- [ ] A1. Provision minimal Azure infrastructure `[Stage 1]`
  - Create Azure AI Foundry workspace and deploy: GPT-4o, text-embedding-3-large, text-embedding-3-small via Azure OpenAI
  - Create Azure Container Apps environment for the MCP server (used when deploying, not required for local dev)
  - All other Azure services (AD, Bot Service, Cosmos DB, Blob Storage, Monitor) are deferred to stream E
  - _Requirements: 1.4_

- [ ] A2. Implement local storage abstraction layer `[Stage 1]`
  - Define `StorageBackend` abstract base class with methods: `store_document(doc: dict)`, `get_document(meeting_id: str, doc_type: str) -> dict`, `store_blob(path: str, data: bytes)`, `get_blob(path: str) -> bytes`, `delete_documents_by_participant(meeting_id: str, participant_id: str)`
  - Implement `LocalStorageBackend`: documents as JSON files under `./data/documents/{meeting_id}/`, blobs under `./data/blobs/{path}`, SQLite index for queries
  - Implement `AzureStorageBackend` as a stub — all methods raise `NotImplementedError` (filled in during stream E)
  - Controlled by `STORAGE_BACKEND=local|azure` env var; default `local`
  - _Note: no Azure storage cost during development_

- [ ] A3. Add participant rate seed data `[Stage 2]`
  - Define `participant_rates` document schema: `{ "id": "rates_{tenant_id}", "type": "participant_rates", "tenant_id": "string", "rates": [{ "participant_id": "string", "display_name": "string", "seniority_level": "string", "hourly_rate": "number", "currency": "string" }] }`
  - Write a seed script that writes a sample document via `StorageBackend.store_document()` — works with both local and Azure backends
  - Also write a sample `participant_roster` fixture under `./fixtures/participant_roster.json` with a mix of internal, external, and C-level participants for use by `MockGraphClient` during local dev
  - _Requirements: 13.1, 16.1_

---

## B. API Layer (MCP Server)

- [ ] B1. Scaffold MCP server and implement Stage 1 tools `[Stage 1]`
  - Scaffold FastAPI application runnable locally with `uvicorn`; `AUTH_ENABLED=false` by default — no token middleware in Stage 1
  - Implement `GraphClient` interface with `MockGraphClient` (returns fixture JSON from `./fixtures/`) and `RealGraphClient` stub; controlled by `GRAPH_BACKEND=mock|real` env var
  - Implement `get_calendar_event(meeting_id)` — delegates to `GraphClient`; returns subject, body, start/end times, attendees
  - Implement `post_adaptive_card(conversation_id, card_json, update_activity_id?)` — delegates to `GraphClient`; mock mode prints card JSON to stdout and returns fake `activity_id`
  - Implement `store_analysis(document)` — delegates to `StorageBackend.store_document()`; validates `type` and `meeting_id` fields present
  - Implement `get_analysis(meeting_id, document_type)` — delegates to `StorageBackend.get_document()`
  - All tool failures return: `{"error": {"code": "...", "message": "...", "retryable": true|false}}`
  - All tools validate input against JSON Schema; return `VALIDATION_ERROR` for non-conforming inputs
  - Note: `get_transcript`, `get_participants`, and `get_participant_roles` are removed — transcript blob URLs pass via A2A, participant data is captured from the Bot join event
  - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5_

  - [ ]* B1.1 Write unit tests for MCP tool input validation
    - Test each tool rejects missing required fields with `VALIDATION_ERROR`
    - Test each tool rejects wrong types with `VALIDATION_ERROR`
    - Test valid inputs are never rejected
    - _Requirements: 19.4_

  - [ ]* B1.2 Write property test: MCP error response structure
    - **Property 20: MCP error response structure**
    - **Validates: Requirements 19.3**

  - [ ]* B1.3 Write property test: MCP input validation rejects invalid inputs
    - **Property 21: MCP input validation rejects invalid inputs**
    - **Validates: Requirements 19.4**

- [ ] B2. Add Stage 2 tools to MCP server `[Stage 2]`
  - Add `send_realtime_alert(conversation_id, alert_type, card_json)` — calls `post_adaptive_card` internally; records alert type and timestamp via `StorageBackend.store_document()` for throttle tracking
  - Add `get_participant_rates(meeting_id)` — reads `participant_rates` document via `StorageBackend.get_document()`
  - Note: `get_participant_roles` is removed — `is_high_value` flag is already in the `participant_roster` document stored by the Bot on join
  - Same input validation and error contract as Stage 1 tools
  - _Requirements: 22.1 (Stage 2), 12.5, 13.1_

- [ ] B3. Add Stage 3 tool to MCP server `[Stage 3]`
  - Add `create_poll(conversation_id, poll_items)` — renders Adaptive Card poll with one entry per action item, each offering "Confirm", "Dispute", "Abstain"; stores poll record via `StorageBackend.store_document()` with `status: "open"` and `closes_at: now + 24h`
  - Same input validation and error contract as previous stages
  - _Requirements: 19.1 (Stage 3), 16.1, 16.2_

---

## C. Teams Integration (Bot Framework)

- [ ] C1. Scaffold Bot Framework app with simulation mode `[Stage 1]`
  - Scaffold Python Bot Framework SDK app with `POST /api/messages` activity handler
  - `BOT_MODE=simulate` by default: expose `POST /dev/simulate_meeting` endpoint that accepts a JSON payload to trigger meeting lifecycle events (join, participant_response, end) locally — no Azure AD or Bot Service needed
  - Create `manifest.json` as a template with placeholder Bot Service app ID (not deployed yet)
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6_

- [ ] C2. Implement consent flow and participant roster capture `[Stage 1]`
  - On meeting join event, enrich each participant from the Bot Framework roster: call Graph `GET /users/{id}` per participant to get title; compare domain against tenant domain to set `is_external`; set `is_high_value: true` if external OR title matches CEO/CTO/CFO/COO/CPO/CMO/CXO/President/VP/Director
  - Store a `participant_roster` document via MCP `store_analysis` containing all enriched participant records — this is the single source of truth for participant data used by all agents
  - Call MCP `post_adaptive_card` to deliver consent Adaptive Card before any transcription begins
  - Store each participant's consent decision (granted/declined/pending) with timestamp and meeting ID via MCP `store_analysis`
  - Treat participants who do not respond within 2 minutes as having declined
  - If consent card cannot be delivered, abort transcription and log the failure with a reason code
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 16.1, 16.2_

  - [ ]* C2.1 Write unit tests for consent card rendering
    - Test consent Adaptive Card JSON contains required disclosure text
    - Test card includes "Accept" and "Decline" action buttons
    - _Requirements: 2.1, 2.2_

- [ ] C3. Implement post-meeting report delivery `[Stage 1]`
  - Receive compiled Analysis Report from Orchestrator Agent
  - Deliver report via MCP `post_adaptive_card` as an Adaptive Card with expandable sections: Agenda Adherence, Time Allocation, Action Items, Sentiment Summary, Participation Summary, Meeting Purpose, Professional Tone Summary
  - Send condensed Action Items card to all consenting participants
  - If report delivery fails or exceeds 10 minutes, send a status message to the organizer
  - _Requirements: 15.2, 15.3, 15.4, 15.5_

- [ ] C4. Implement real-time Meeting Cost Tracker `[Stage 2]`
  - On meeting join, retrieve participant rates via MCP `get_participant_rates` and store in meeting state
  - Every 60 seconds, calculate `Meeting_Cost = sum(elapsed_hours × hourly_rate)` for participants with available rate data
  - Render Meeting Cost Tracker Adaptive Card: total cost, elapsed time, active participant count, per-participant breakdown, excluded participants note
  - First render: call `post_adaptive_card` and store returned `activity_id`; subsequent updates: call with `update_activity_id` to update in place
  - Every 5 minutes, persist a `cost_snapshot` document via MCP `store_analysis`; `snapshot_index` increments by 1, `elapsed_minutes` increments by 5
  - Include `final_meeting_cost` in Analysis Report when meeting ends
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [ ]* C4.1 Write property test: meeting cost calculation correctness
    - **Property 15: Meeting cost calculation correctness**
    - **Validates: Requirements 13.2, 13.5**

  - [ ]* C4.2 Write property test: cost snapshot count invariant
    - **Property 16: Cost snapshot count invariant**
    - **Validates: Requirements 13.7**

  - [ ]* C4.3 Write unit tests for cost calculation with missing rates
    - Test participants without rate data are excluded from total cost
    - Test `excluded_participant_count` equals number of participants with null rates
    - Test card renders correctly when all participants have missing rates
    - _Requirements: 13.5_

- [ ] C4a. Implement Participation Pulse card and silent participant alerts `[Stage 2]`
  - Every 5 minutes, receive participation snapshot from Orchestrator (which gets it from Sentiment Agent via A2A)
  - Render Participation Pulse Adaptive Card: active speakers list, silent participants list, per-participant engagement indicator, overall energy level (High/Medium/Low)
  - First render: call MCP `post_adaptive_card` and store `activity_id`; subsequent updates: call with `update_activity_id` to update in place
  - When Orchestrator signals a participant has been silent >10 minutes: send private Real_Time_Alert to organizer only via MCP `send_realtime_alert` with `alert_type: "silent_participant"`
  - _Requirements: 15.1–15.4, 15.7, 15.8_

- [ ] C5. Implement consent poll delivery and report update `[Stage 3]`
  - After delivering Analysis Report, call MCP `create_poll` with one entry per action item; store returned `poll_id` in report document
  - Collect poll responses; update action item `poll_responses` map via MCP `store_analysis`
  - After 24 hours, close poll; re-evaluate each action item: if "Dispute" count > ("Confirm" + "Abstain") count → set status "Disputed by Poll"
  - Update stored Analysis Report with aggregated poll results and reclassified statuses
  - Notify meeting organizer when poll closes with response summary
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [ ]* C5.1 Write property test: poll structure completeness
    - **Property 17: Poll structure completeness**
    - **Validates: Requirements 16.2**

  - [ ]* C5.2 Write property test: disputed-by-poll majority rule
    - **Property 18: Disputed-by-poll majority rule**
    - **Validates: Requirements 16.5**

  - [ ]* C5.3 Write unit tests for poll majority edge cases
    - Test "Disputed by Poll" when Dispute count strictly greater than Confirm + Abstain
    - Test not "Disputed by Poll" on a tie
    - Test not "Disputed by Poll" when all abstain
    - Test with single participant who disputes
    - _Requirements: 16.5_

---

## D. AI Agents

- [ ] D1. Implement Transcription Agent `[Stage 1]`
  - Create Semantic Kernel agent in Azure AI Foundry
  - Connect to Graph Communications API (`/communications/calls/{id}/transcripts`) for live transcript stream
  - Attribute each segment to correct participant via Teams identity; populate `participant_id`, `participant_name`, `start_time`, `end_time`, `duration_seconds`, `consent_verified`
  - Check consent record before storing any segment — omit segments from participants who declined
  - Buffer and persist segments via MCP `store_analysis` every ≤60 seconds as `raw_transcript.jsonl`
  - On Graph API disconnect: reconnect within 10 seconds; log gap with start/end timestamps
  - On meeting end: finalize to `final_transcript.json`, notify Orchestrator via A2A
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* D1.1 Write property test: transcript segment attribution invariant
    - **Property 4: Transcript segment attribution invariant**
    - **Validates: Requirements 3.2**

  - [ ]* D1.2 Write property test: transcript persistence latency invariant
    - **Property 5: Transcript persistence latency invariant**
    - **Validates: Requirements 3.4**

- [ ] D2. Implement Analysis Agent — core `[Stage 1]`
  - Create Semantic Kernel agent in Azure AI Foundry
  - Retrieve calendar event via MCP `get_calendar_event`; extract agenda as ordered list of topic strings (max 200 chars, non-null, non-empty)
  - If no agenda in calendar event, infer from first 10% of transcript using GPT-4o; if fails, set `agenda_source: "not_determined"`
  - Pre-compute `text-embedding-3-large` embeddings for each agenda topic
  - Compute in-memory cosine similarity (numpy) between agenda topic embeddings and transcript segment embeddings
  - Classify each topic: "Covered" (≥0.6), "Partially Covered" (≥0.35), "Not Covered" (<0.35); score must be in [0.0, 1.0]
  - Identify segments with max similarity <0.35 across all topics → "Off-Agenda Discussion"
  - Calculate time in minutes and percentage per agenda topic and preamble; percentages must sum to 100% (±0.1%)
  - Flag meetings >120 minutes as "Extended Duration"
  - Extract action items via GPT-4o structured output: description, owner, due date (ISO8601 or "Not Specified"), transcript timestamp, status ("Proposed"/"Confirmed")
  - Group action items by owner; persist result via MCP `store_analysis`
  - _Requirements: 4.1–4.4, 5.1–5.4, 6.1–6.4, 7.1–7.5_

  - [ ]* D2.1 Write property test: agenda topic length invariant
    - **Property 6: Agenda topic length invariant** — **Validates: Requirements 4.3**

  - [ ]* D2.2 Write property test: similarity score range invariant
    - **Property 7: Similarity score range invariant** — **Validates: Requirements 5.1**

  - [ ]* D2.3 Write property test: agenda classification completeness
    - **Property 8: Agenda classification completeness** — **Validates: Requirements 5.2**

  - [ ]* D2.4 Write property test: time allocation percentages sum to 100
    - **Property 9: Time allocation percentages sum to 100** — **Validates: Requirements 6.3**

  - [ ]* D2.5 Write property test: action item schema completeness
    - **Property 10: Action item schema completeness** — **Validates: Requirements 7.1–7.4**

  - [ ]* D2.6 Write unit tests for agenda extraction
    - Test extraction from bulleted agenda in calendar body
    - Test extraction from numbered agenda in calendar body
    - Test fallback to transcript inference when calendar body is empty
    - Test "Agenda: Not Determined" when both sources fail
    - _Requirements: 4.1, 4.2, 4.4_

  - [ ]* D2.7 Write unit tests for action item schema validation
    - Test all required fields present on extracted items
    - Test "Not Specified" due date when no date mentioned
    - Test "Proposed" vs "Confirmed" based on agreement markers
    - _Requirements: 7.2, 7.3, 7.4_

- [ ] D3. Implement Sentiment Agent — core `[Stage 1]`
  - Create Semantic Kernel agent in Azure AI Foundry
  - Call Azure AI Language Sentiment Analysis API per participant's concatenated segments; classify "Positive"/"Neutral"/"Negative"; classify "Insufficient Data" if <50 words
  - Identify sentiment shifts within participant contributions; record transcript timestamp of each shift
  - Calculate speaking time percentage and turn count per participant
  - Flag <2% speaking time → "Low Participation"; >50% → "Dominant Speaker" (mutually exclusive)
  - Rank participants by speaking time percentage descending
  - Persist participation summary via MCP `store_analysis`
  - _Requirements: 9.1–9.5, 10.1–10.5_

  - [ ]* D3.1 Write property test: sentiment classification validity
    - **Property 11: Sentiment classification validity** — **Validates: Requirements 9.1, 9.5**

  - [ ]* D3.2 Write property test: speaking time percentages sum to 100
    - **Property 12: Speaking time percentages sum to 100** — **Validates: Requirements 10.1**

  - [ ]* D3.3 Write property test: participation flagging thresholds
    - **Property 13: Participation flagging thresholds** — **Validates: Requirements 10.4, 10.5**

- [ ] D4. Implement Orchestrator Agent — Stage 1 lifecycle `[Stage 1]`
  - Create Semantic Kernel agent in Azure AI Foundry as top-level orchestrator
  - On `meeting_start`: retrieve calendar event via MCP, trigger consent card, dispatch `capture_transcript_segment` to Transcription Agent every 60 seconds via A2A
  - On `meeting_end`: dispatch `finalize_transcript` to Transcription Agent; then dispatch `analyze_meeting` to Analysis Agent and `analyze_sentiment` to Sentiment Agent in parallel
  - If specialist agent does not respond within 120 seconds: retry once; on second failure mark section "Unavailable"
  - Aggregate results; compile Analysis Report conforming to defined data model
  - Deliver report via MCP `post_adaptive_card` within 10 minutes; if exceeded, send status message to organizer
  - Log all A2A dispatches and responses with timestamps
  - _Requirements: 15.1–15.5, 18.1–18.4_

  - [ ]* D4.1 Write property test: consent precedes transcription
    - **Property 1: Consent precedes transcription** — **Validates: Requirements 2.1, 2.4**

  - [ ]* D4.2 Write property test: consent exclusion is total
    - **Property 2: Consent exclusion is total** — **Validates: Requirements 2.3, 3.5**

  - [ ]* D4.3 Write property test: consent record round-trip
    - **Property 3: Consent record round-trip** — **Validates: Requirements 2.5**

- [ ] D5. Implement Orchestrator Agent — real-time evaluation loop `[Stage 2]`
  - Extend 60-second loop: take last 120 seconds of transcript (sliding window), concatenate text, compute cosine similarity against pre-computed agenda topic embeddings using `text-embedding-3-small`
  - If max similarity <0.35 for 3 consecutive windows → call MCP `send_realtime_alert` type `off_track`
  - At T=5min: if no topic has similarity >0.4 in any window → `send_realtime_alert` type `agenda_unclear_5min`
  - At T=8min: if agenda still unclear → generate suggested agenda via GPT-4o → `send_realtime_alert` type `agenda_unclear_10min`
  - Throttle: read last alert timestamp via `StorageBackend.get_document()` before sending; max 1 alert per type per 5-minute window
  - _Requirements: 12.1–12.7_

  - [ ]* D5.1 Write property test: real-time alert rate limiting
    - **Property 14: Real-time alert rate limiting** — **Validates: Requirements 12.6**

  - [ ]* D5.2 Write unit tests for real-time evaluation thresholds
    - Test off-track triggers after exactly 3 consecutive windows below 0.35
    - Test off-track does not trigger after only 2 consecutive windows
    - Test agenda-unclear triggers at T=5min when no topic exceeds 0.4
    - Test agenda-unclear does not trigger when at least one topic exceeds 0.4
    - _Requirements: 12.2–12.4_

- [ ] D5a. Implement Meeting Purpose Detection in Orchestrator Agent `[Stage 2]`
  - On meeting join, retrieve calendar event subject and description via MCP `get_calendar_event`; store as initial purpose hypothesis
  - At T=2min, take first 2 minutes of transcript segments; prompt GPT-4o with calendar context + transcript to classify Meeting_Purpose as one of: "Decision meeting", "Status update", "Brainstorming", "Client presentation", "Problem-solving"
  - If detected purpose conflicts with calendar subject, set `meeting_purpose_mismatch: true` in meeting record
  - Surface classified purpose as Real_Time_Alert Adaptive Card to all participants via MCP `send_realtime_alert`
  - Every 5 minutes, re-evaluate purpose alignment; if diverged for >5 consecutive minutes, send Real_Time_Alert noting divergence
  - Persist `meeting_purpose` and `meeting_purpose_mismatch` to meeting record via MCP `store_analysis`
  - _Requirements: 14.1–14.7_

  - [ ]* D5a.1 Write property test: meeting purpose classification validity
    - **Property 22: Meeting purpose classification validity** — **Validates: Requirements 14.2**

  - [ ]* D5a.2 Write unit tests for purpose mismatch detection
    - Test mismatch flag set when detected purpose differs from calendar subject
    - Test no mismatch flag when detected purpose aligns with calendar subject
    - _Requirements: 14.4_

- [ ] D5b. Implement Participation Pulse in Sentiment Agent `[Stage 2]`
  - Every 5 minutes, compute participation snapshot: list of participants who have spoken, list who have not yet spoken, speaking time distribution
  - Calculate overall meeting energy level (High/Medium/Low) from aggregate of speaking frequency, turn count, and available audio engagement signals
  - Respond to Orchestrator A2A dispatch `compute_participation_pulse` with structured response (active_speakers, silent_participants, energy_level, per_participant_engagement)
  - Detect participants silent for >10 consecutive minutes; include in response so Orchestrator can send private organizer alert
  - Detect significant pitch/tone shifts in real time (if audio available); log with participant identity and transcript timestamp — do NOT trigger any meeting-wide alert
  - _Requirements: 15.1–15.8_

  - [ ]* D5b.1 Write property test: participation pulse snapshot interval
    - **Property 26: Participation pulse snapshot interval** — **Validates: Requirements 15.1, 15.3**

  - [ ]* D5b.2 Write unit tests for energy level calculation
    - Test "High" energy when majority of participants have spoken recently
    - Test "Low" energy when majority of participants have been silent >5 minutes
    - Test energy level falls back to transcript-only signals when audio unavailable
    - _Requirements: 15.7, 15.8_

- [ ] D5c. Implement Professional Tone Monitoring in Orchestrator Agent `[Stage 2]`
  - On meeting join, read `participant_roster` document from storage via `get_analysis`; if any participant has `is_high_value: true`, set `high_value_participant_mode: true` in meeting record
  - Every 60 seconds, analyze last 60 seconds of transcript segments for Tone_Issues: aggressive language, dismissive language, interruptions, profanity, disrespectful tone
  - Classify each detected issue: "Minor" | "Moderate" | "Severe"; in High-Value Participant Mode, treat "Minor" as "Moderate"
  - On "Moderate" or "Severe": send private Real_Time_Alert to organizer only via MCP `send_realtime_alert` with `alert_type: "tone_private"` — include severity, issue type, and participant ID
  - If same participant triggers same severity within 3 minutes of prior private alert: send whole-meeting constructive alert via `send_realtime_alert` with `alert_type: "tone_public"` — alert text must NOT name the participant or quote the statement
  - Log ALL detected Tone_Issues to meeting record via MCP `store_analysis` regardless of whether alert was sent
  - _Requirements: 16.1–16.10_

  - [ ]* D5c.1 Write property test: high-value participant mode activation
    - **Property 23: High-value participant mode activation** — **Validates: Requirements 16.1, 16.2**

  - [ ]* D5c.2 Write property test: tone issue private-before-public escalation
    - **Property 24: Tone issue private-before-public escalation** — **Validates: Requirements 16.6, 16.7**

  - [ ]* D5c.3 Write property test: whole-meeting tone alert anonymity
    - **Property 25: Whole-meeting tone alert anonymity** — **Validates: Requirements 16.8**

  - [ ]* D5c.4 Write unit tests for tone severity classification
    - Test "Minor" issue escalated to "Moderate" in High-Value Participant Mode
    - Test "Minor" issue NOT escalated in standard mode
    - Test private alert sent on first "Moderate" detection
    - Test whole-meeting alert sent only after prior private alert within 3 minutes
    - _Requirements: 16.4, 16.5, 16.6, 16.7_

- [ ] D6. Implement Transcription Agent — batch audio post-processing `[Stage 3]`
  - After meeting ends and final transcript is persisted, trigger Azure AI Speech batch API with stored audio blob URL
  - Poll batch job until complete; extract per-participant prosody: `speaking_rate_wpm`, `pitch_mean_hz`, `pitch_variance`
  - Correlate prosody with transcript timestamps and participant identities; update `prosody` fields in transcript segment documents
  - Persist enriched data as `tone_pitch_features.json` in storage
  - Notify Orchestrator via A2A when complete; on failure, log and set participant prosody fields to null
  - _Requirements: 14.1–14.5_

- [ ] D7. Implement Analysis Agent — agreement detection and relevance `[Stage 3]`
  - Analyze transcript for linguistic markers of agreement ("agreed", "will do", "confirmed"), disagreement ("disagree", "not sure"), and ambiguity per action item and key decision
  - Assign each action item: "Agreed", "Disputed", or "Unresolved"; include supporting transcript excerpts and disagreeing participant names
  - Compute relevance score per participant: `(agenda_aligned_speaking_time / total_speaking_time) × 100` where aligned = segments with cosine similarity ≥0.4 to nearest agenda topic
  - Classify: ≥60% → "Highly Relevant", ≥30% → "Relevant", <30% → "Low Relevance", 0 speaking time → "Observer"
  - Read participant job titles from the stored `participant_roster` document via `get_analysis` — no additional Graph API call needed
  - _Requirements: 8.1–8.4, 11.1–11.4_

  - [ ]* D7.1 Write unit tests for agreement detection
    - Test "Agreed" when strong agreement markers present
    - Test "Disputed" when disagreement markers present
    - Test "Unresolved" when ambiguous with no resolution
    - _Requirements: 8.1, 8.2_

  - [ ]* D7.2 Write unit tests for relevance formula
    - Test "Highly Relevant" when aligned time ≥60%
    - Test "Relevant" when aligned time 30–60%
    - Test "Low Relevance" when aligned time <30%
    - Test "Observer" when total speaking time is 0
    - _Requirements: 11.2–11.4_

- [ ] D8. Extend Sentiment Agent — prosody and opinion mining `[Stage 3]`
  - After Orchestrator signals audio post-processing complete, incorporate prosody signals as raw numeric values in `participation_summary.prosody`
  - Call Azure AI Language Opinion Mining API per participant; populate `opinion_mining_aspects` with aspect-level sentiment
  - Compute `contribution_score` combining speaking time %, turn count, and prosody signals (numeric, no custom labels)
  - _Requirements: 9.6–9.8, 10.6–10.7_

---

## E. Production Wiring (after full MVP validated locally)

- [ ] E1. Provision Azure storage and implement AzureStorageBackend
  - Create Azure Cosmos DB account (serverless) with containers: `meetings` (partition `/meeting_id`), `analysis` (partition `/meeting_id`), `config` (partition `/tenant_id`); custom indexing on `analysis`
  - Create Azure Blob Storage account; containers: `transcripts`, `reports`, `exports` (Cool tier, lifecycle auto-delete policy, default 90 days)
  - Implement `AzureStorageBackend`: `store_document` → Cosmos DB upsert, `get_document` → Cosmos DB point read, `store_blob` → Blob upload, `get_blob` → Blob download, `delete_documents_by_participant` → Cosmos DB + Blob delete
  - Switch `STORAGE_BACKEND=azure`; verify all flows work with real storage
  - _Requirements: 17.1–17.5, 20.1, 20.2_

  - [ ]* E1.1 Write property test: consent revocation deletes all participant data
    - **Property 19: Consent revocation deletes all participant data** — **Validates: Requirements 17.4**

  - [ ]* E1.2 Write unit tests for consent revocation
    - Test transcript segments deleted from storage after revocation
    - Test analysis report regenerated after revocation
    - _Requirements: 17.4_

- [ ] E2. Register Azure AD app and wire authentication
  - Register single-tenant Azure AD app with permissions: `OnlineMeetings.ReadWrite.All`, `Calendars.Read`, `CallRecords.Read.All`, `Chat.ReadWrite.All`, `User.Read.All`, `OnlineMeetingTranscript.Read.All`
  - Implement `RealGraphClient` using Microsoft Graph Python SDK with managed identity token acquisition
  - Add managed identity token validation middleware to MCP server; switch `AUTH_ENABLED=true`, `GRAPH_BACKEND=real`
  - _Requirements: 1.1, 1.2, 19.5_

- [ ] E3. Deploy Bot Service and wire Teams integration
  - Create Azure Bot Service; link to AD app registration; update `manifest.json` with real Bot Service app ID
  - Subscribe to Graph `calendarView` change notifications via webhook; implement auto-join at meeting start via `createCall`
  - If auto-join fails within 60 seconds: log failure with meeting ID and reason code; notify organizer
  - Switch `BOT_MODE=teams`; deploy Teams App Manifest to tenant
  - Create Azure Monitor workspace; configure diagnostic settings for all resources
  - _Requirements: 1.1, 1.3, 1.5, 1.6, 20.4_

- [ ] E4. End-to-end production smoke test
  - Run full Stage 1 + 2 + 3 flow against a real Teams meeting with all env vars set to production
  - Verify consent flow, transcription, real-time alerts, cost tracker, post-meeting report, and poll all work end-to-end
  - _Requirements: all_

---

## F. Phase 2 — Post-MVP

- [ ]* F1. Provision Phase 2 Azure infrastructure
  - Azure Static Web App for dashboard; Azure AI Search (Basic tier) for embeddings; Azure AD SSO app registration
  - _Requirements: 21.3, 21.4_

- [ ]* F2. Set up Azure AI Search embeddings index
  - Define `agenda-embeddings` index: `meeting_id`, `topic_text`, `embedding` (3072-dim vector, HNSW profile, cosine similarity)
  - Write backfill script to index existing agenda embeddings from storage
  - _Requirements: 21.1_

- [ ]* F3. Implement historical analysis dashboard
  - React + Fluent UI v9 app on Azure Static Web App; Azure AD SSO via MSAL React
  - Aggregated metrics views: agenda adherence, cost, participation trends — filterable by participant/team/meeting type
  - Data via lightweight Azure Functions API layer over Cosmos DB `analysis` container
  - _Requirements: 21.1–21.4_

- [ ]* F4. Implement PM tool integration
  - Config-driven: `planner` or `jira` in storage `config` container
  - On action item confirmed: call Planner `POST /planner/tasks` or Jira `POST /rest/api/3/issue`; map owner to PM tool user
  - On sync failure: log, notify organizer, retain item in report
  - _Requirements: 22.1–22.3_

- [ ]* F5. Implement video analysis pipeline
  - On meeting end, if video available and tenant policy permits: store video in Blob Storage Cool tier
  - Separate consent Adaptive Card for video analysis
  - Trigger Azure AI Vision; extract per-participant engagement signals correlated with transcript timestamps
  - Include video engagement summary in Analysis Report
  - _Requirements: 23.1–23.4_

---

## Notes

- Tasks marked `*` are optional
- Sub-tasks marked `*` are optional property/unit tests
- Property tests use `hypothesis` with `@settings(max_examples=100)` and tag comment: `# Feature: teams-meeting-analysis-bot, Property {N}: {property_title}`
- Streams A, B, C, D can be worked in parallel within each stage — D depends on B (MCP server) being available first
- Stream E is a single production wiring sprint done after all of A–D are validated locally
- Stream F is post-MVP and fully independent
