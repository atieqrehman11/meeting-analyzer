# Requirements Document

## Introduction

The Teams Meeting Analysis Bot is an AI-powered agent integrated into Microsoft Teams that automatically joins meetings, captures transcripts with participant consent, and delivers proactive real-time insights during the meeting — then performs deep post-meeting analysis. The key differentiators are the real-time proactive capabilities: the bot actively monitors the meeting as it happens, detecting and surfacing the meeting's purpose and objective within the first 2 minutes, monitoring professional tone with heightened sensitivity when high-value participants (external clients or C-level executives) are present, tracking live participation dynamics via a Participation Pulse, detecting when the agenda is unclear, when discussion goes off-track, and surfacing live cost and engagement signals to participants. Post-meeting analysis covers agenda adherence, time allocation, action items, tone and pitch analysis, participant sentiment, engagement levels, and relevance of attendees. Results are delivered via an interactive post-meeting report with a consent/validation poll so participants can confirm or dispute the AI's findings.

Delivery follows a 3-stage incremental approach: Stage 1 (Weeks 1–2) establishes the "Proof of Value" foundation with auto-join, consent, transcription, agenda extraction, and post-meeting summary; Stage 2 (Weeks 3–4) adds "Real-Time Intelligence" with proactive in-meeting alerts and a live cost tracker; Stage 3 (Weeks 5–6) delivers "Deep Analysis" with sentiment, tone and pitch, participant agreement detection, relevance assessment, and consent polls. A Phase 2 post-MVP track covers video analysis, historical dashboards, and PM tool integrations.

This document also captures architectural guidance to inform the design phase, including agent topology, model selection, framework choices, storage strategy, A2A communication patterns, and MCP tooling.

---

## Architectural Context

This section answers the user's architectural questions. These inform requirements but are not requirements themselves — they will be elaborated in the design document.

### How Many Agents (Azure AI Foundry)

A multi-agent architecture with 4 specialized agents is recommended:

1. **Orchestrator Agent** — coordinates the pipeline, routes tasks to specialist agents, aggregates results
2. **Transcription & Notes Agent** — manages real-time transcript capture, speaker diarization, and raw note generation
3. **Analysis Agent** — performs agenda adherence, time allocation, action item extraction, and participant relevance analysis
4. **Sentiment & Engagement Agent** — performs per-participant sentiment scoring and participation measurement

All agents are hosted in Azure AI Foundry as Agent Service deployments. The Orchestrator uses A2A (Agent-to-Agent) protocol to delegate tasks and collect results.

### Recommended Models

| Task | Model |
|---|---|
| Transcription | Azure AI Speech Service (real-time + batch) |
| Summarization, agenda extraction, action items | GPT-4o (via Azure OpenAI) |
| Sentiment, tone & pitch analysis | GPT-4o or Azure AI Language (Sentiment Analysis API) |
| Participation scoring | GPT-4o with structured output |
| Embedding / semantic similarity (agenda vs discussion) | text-embedding-3-large |
| Audio tone & pitch feature extraction | Azure AI Speech Service (prosody analysis) |

GPT-4o is the primary reasoning model. Azure AI Language service handles lower-cost sentiment tasks where fine-grained LLM reasoning is not required.

### MVP vs Extended Approach

**Stage 1 — Proof of Value (Weeks 1–2):**
- Bot auto-joins meetings based on calendar events (no manual invite required)
- Participant consent enforced before transcription begins
- Participant roster captured and enriched on join (domain, title, is_external, is_high_value) — stored as a single document, reused by all agents
- Transcript captured via Teams Graph API / Bot Framework with speaker attribution (text only)
- Agenda extraction from calendar event or inferred from transcript
- Post-meeting analysis delivered as an Adaptive Card: agenda adherence, action items, participation breakdown
- Basic storage: Azure Blob Storage (transcripts) + Azure Cosmos DB (analysis results)
- A2A orchestration foundation with Orchestrator and specialist agents
- MCP server with core tools: `get_calendar_event`, `post_adaptive_card`, `store_analysis`, `get_analysis`
- Privacy and compliance basics (retention, consent, data residency)

**Stage 2 — Real-Time Intelligence (Weeks 3–4):**
- Real-time proactive insights: agenda clarity alerts, off-track detection, refocus reminders
- Real-time Meeting Purpose and Objective Detection: classify meeting type within first 2 minutes and surface as a Real_Time_Alert card
- Real-time Agenda Availability and Adherence Alert: immediate check for agenda on join, missing-agenda alert with suggested template within 30 seconds
- Real-time Voice Pitch, Tone, and Audience Participation Insights: Participation Pulse card every 5 minutes, silent participant alerts, pitch/tone shift logging, meeting energy indicator
- Real-time Professional Tone Monitoring: continuous tone monitoring, severity classification, High-Value Participant Mode with heightened sensitivity, private organizer alerts and escalation to whole-meeting alerts
- Real-Time Meeting Cost Tracker displayed as an Adaptive Card during the meeting
- MCP server extended with: `send_realtime_alert`, `get_participant_rates`

**Stage 3 — Deep Analysis (Weeks 5–6):**
- Sentiment, tone and pitch analysis (audio signals added to transcription pipeline)
- Participant agreement detection on action items and decisions
- Participant relevance assessment relative to agenda
- Consent poll for participant validation of action items
- Audio post-processing for enriched prosody analysis

**Phase 2 (Post-MVP):**
- Video data analysis (facial expressions, attention signals)
- Dashboard web app for historical analysis
- Per-user sentiment trend tracking
- Integration with project management tools (Planner, Jira) for action item sync

### Framework Choices

| Layer | Technology |
|---|---|
| Bot / Teams integration | Microsoft Bot Framework SDK (Node.js or Python) + Teams AI Library |
| Agent orchestration | Azure AI Foundry Agent Service + Semantic Kernel (Python) |
| Backend API | FastAPI (Python) — lightweight, async, OpenAPI-native |
| Frontend dashboard (Phase 2) | React + Fluent UI v9 |
| A2A communication | Azure AI Foundry A2A protocol over HTTP with agent endpoints |
| MCP tooling | Model Context Protocol server exposing tools: `get_calendar_event`, `post_adaptive_card`, `store_analysis`, `get_analysis`, `get_participant_rates`, `send_realtime_alert`, `create_poll` |

### Storage Strategy (Cost-Effective)

| Data | Storage | Rationale |
|---|---|---|
| Raw transcripts | Azure Blob Storage (Cool tier) | Cheap, durable, infrequent access |
| Analysis results, action items | Azure Cosmos DB (serverless) | Pay-per-request, JSON-native |
| Meeting metadata | Azure Cosmos DB (serverless) | Same container as analysis |
| Embeddings (agenda similarity) | Azure AI Search (Basic tier) | Vector search, low cost at small scale |
| Polls / consent responses | Azure Cosmos DB (serverless) | Consistent with other structured data |

### A2A Communication

The Orchestrator Agent communicates with specialist agents using the Azure AI Foundry A2A protocol. Each specialist agent exposes an HTTP endpoint registered in the Foundry Agent catalog. The Orchestrator sends structured task messages and awaits structured responses. Agents do not call each other directly — all routing goes through the Orchestrator.

### MCP Tools Required

The MCP server exposes the following tools to agents:

| Tool | Description |
|---|---|
| `get_calendar_event` | Fetch meeting metadata and agenda from Graph API |
| `post_adaptive_card` | Send an Adaptive Card to a Teams channel or chat |
| `create_poll` | Create a Teams poll (via Forms or Adaptive Card) |
| `store_analysis` | Persist analysis results to storage |
| `get_analysis` | Retrieve prior analysis results |
| `get_participant_rates` | Retrieve seniority level and hourly rate for each participant for cost calculation |
| `send_realtime_alert` | Send a proactive in-meeting notification or reminder as an Adaptive Card |

Note: `get_transcript`, `get_participants`, and `get_participant_roles` are removed. Transcript blob URLs pass via A2A. Participant data is captured from the Bot Framework join event and stored as a `participant_roster` document — all agents read from that.

---

## Glossary

- **Bot**: The Microsoft Teams bot application built on Bot Framework SDK
- **Orchestrator_Agent**: The top-level AI agent that coordinates all specialist agents
- **Transcription_Agent**: The specialist agent responsible for capturing and processing meeting transcripts
- **Analysis_Agent**: The specialist agent responsible for agenda, action item, and participant relevance analysis
- **Sentiment_Agent**: The specialist agent responsible for per-participant sentiment and engagement scoring
- **MCP_Server**: The Model Context Protocol server that exposes tools to agents
- **Transcript**: The time-stamped, speaker-attributed text record of a meeting
- **Agenda**: The list of topics provided in the meeting invitation or extracted from the meeting description
- **Action_Item**: A task or commitment identified during the meeting, attributed to one or more participants
- **Adaptive_Card**: A Teams UI component used to display structured information and collect responses
- **Poll**: A structured survey sent to meeting participants to confirm or dispute analysis findings
- **Participant**: A person who attended the meeting as identified by their Teams identity
- **Consent**: Explicit opt-in permission from a participant to record and analyze their contributions
- **Analysis_Report**: The structured output produced by the Analysis_Agent and Sentiment_Agent after a meeting ends
- **A2A**: Agent-to-Agent communication protocol used within Azure AI Foundry
- **Real_Time_Alert**: A proactive in-meeting notification sent by the bot as an Adaptive Card to surface insights or reminders while the meeting is in progress
- **Meeting_Cost**: The estimated dollar value consumed by a meeting, calculated from participant count, seniority-based hourly rates, and elapsed meeting time
- **Tone_Analysis**: Assessment of the emotional quality and manner of speech (e.g., assertive, hesitant, collaborative) derived from audio prosody and linguistic features
- **Pitch_Analysis**: Measurement of vocal pitch patterns in participant audio to detect stress, confidence, or engagement signals
- **Meeting_Purpose**: The classified primary objective of a meeting (e.g., "Decision meeting", "Status update", "Brainstorming", "Client presentation", "Problem-solving") as detected by the bot from opening statements and calendar context
- **Participation_Pulse**: A live Adaptive Card surfaced in the meeting chat every 5 minutes showing active speakers, silent participants, per-participant engagement indicators, and overall meeting energy level
- **High_Value_Participant**: A meeting participant identified as either external to the tenant (non-tenant domain) or holding a C-level or senior title (CEO, CTO, CFO, COO, CPO, CMO, CXO, President, VP, Director); triggers heightened tone monitoring sensitivity
- **Tone_Issue**: A detected instance of aggressive, dismissive, profane, or disrespectful language or tone in the meeting, classified by severity as "Minor", "Moderate", or "Severe"
- **Professional_Tone_Mode**: The standard tone monitoring mode applied to all meetings; when a High_Value_Participant is present, the bot activates heightened sensitivity where "Minor" issues are escalated to "Moderate"

---

## Requirements

> **Stage Legend**
> - `[Stage 1 - Proof of Value]` — Weeks 1–2: core bot, consent, transcription, agenda, post-meeting summary, storage, A2A foundation, MCP core tools, privacy basics
> - `[Stage 2 - Real-Time Intelligence]` — Weeks 3–4: proactive in-meeting alerts, real-time cost tracker, extended MCP tools
> - `[Stage 3 - Deep Analysis]` — Weeks 5–6: sentiment/tone/pitch, agreement detection, relevance assessment, consent poll, audio post-processing
> - `[Phase 2]` — Post-MVP: video analysis, historical dashboard, PM tool integrations

---

### Requirement 1: Bot Registration and Teams Integration `[Stage 1 - Proof of Value]`

**User Story:** As a Teams administrator, I want to register and deploy the bot in our Microsoft Teams tenant, so that the bot can automatically join scheduled meetings and organizers can also invite it manually.

#### Acceptance Criteria

1. THE Bot SHALL be registered as a Microsoft Teams application via the Azure Bot Service and Teams App Manifest.
2. THE Bot SHALL authenticate with Microsoft Graph API using an Azure AD application identity with the minimum required delegated and application permissions.
3. WHEN a Teams administrator installs the bot, THE Bot SHALL be available for meeting organizers to invite to scheduled meetings.
4. THE Bot SHALL support deployment to a single Teams tenant (single-tenant Azure AD app registration) for the MVP.
5. WHEN a calendar event is created or updated in the tenant, THE Bot SHALL retrieve the event via the MCP_Server `get_calendar_event` tool and automatically join the meeting at the scheduled start time without requiring a manual invite.
6. IF the Bot fails to auto-join a scheduled meeting within 60 seconds of the start time, THEN THE Bot SHALL log the failure with the meeting ID and reason code and notify the meeting organizer via a Teams message.

---

### Requirement 2: Participant Consent `[Stage 1 - Proof of Value]`

**User Story:** As a meeting participant, I want to be informed and give consent before my speech is recorded and analyzed, so that my privacy is respected.

#### Acceptance Criteria

1. WHEN the Bot joins a meeting, THE Bot SHALL send a consent notification message in the meeting chat visible to all participants before any recording or transcription begins.
2. THE consent notification SHALL state clearly that the meeting will be transcribed and analyzed by an AI system.
3. WHEN a participant explicitly declines consent, THE Bot SHALL exclude that participant's utterances from the transcript and all downstream analysis.
4. IF the Bot is unable to send the consent notification, THEN THE Bot SHALL not begin transcription and SHALL log the failure with a reason code.
5. THE Bot SHALL store each participant's consent decision with a timestamp and meeting ID in the Consent_Store.
6. WHERE a tenant-level policy mandates recording consent, THE Bot SHALL enforce that policy before transcription begins.

---

### Requirement 3: Real-Time Transcription, Note Taking, and Audio Analysis `[Stage 1 - Proof of Value / Stage 3 - Deep Analysis]`

**User Story:** As a meeting organizer, I want the bot to capture a transcript with speaker attribution and analyze tone and pitch during the meeting, so that the analysis has accurate source material and real-time audio signals.

#### Acceptance Criteria

1. `[Stage 1]` WHEN a meeting starts and all required consents are obtained, THE Transcription_Agent SHALL begin capturing the meeting transcript via the Microsoft Graph Communications API.
2. `[Stage 1]` THE Transcription_Agent SHALL attribute each transcript segment to the correct Participant using their Teams identity.
3. `[Stage 1]` THE Transcription_Agent SHALL record a timestamp for the start and end of each transcript segment.
4. `[Stage 1]` WHILE a meeting is in progress, THE Transcription_Agent SHALL buffer transcript segments and persist them to Blob Storage at intervals not exceeding 60 seconds.
5. `[Stage 1]` WHEN a participant who declined consent speaks, THE Transcription_Agent SHALL omit that participant's audio segments from the transcript.
6. `[Stage 1]` IF the transcription service connection is interrupted, THEN THE Transcription_Agent SHALL attempt to reconnect within 10 seconds and SHALL log the gap in coverage with start and end timestamps.
7. `[Stage 1]` WHEN the meeting ends, THE Transcription_Agent SHALL finalize and persist the complete Transcript to Blob Storage and notify the Orchestrator_Agent.
8. `[Stage 3]` WHILE a meeting is in progress, THE Transcription_Agent SHALL extract Tone_Analysis and Pitch_Analysis signals from each consenting Participant's audio using the Azure AI Speech Service prosody analysis capability.
9. `[Stage 3]` THE Transcription_Agent SHALL associate each Tone_Analysis and Pitch_Analysis data point with the corresponding Participant identity and Transcript timestamp.
10. `[Stage 3]` WHILE a meeting is in progress, THE Transcription_Agent SHALL persist tone and pitch data points to Blob Storage at intervals not exceeding 60 seconds alongside transcript segments.

---

### Requirement 4: Agenda Extraction `[Stage 1 - Proof of Value]`

**User Story:** As a meeting organizer, I want the bot to identify the meeting agenda, so that the analysis can measure how well the discussion stayed on topic.

#### Acceptance Criteria

1. WHEN a meeting ends, THE Analysis_Agent SHALL retrieve the meeting's calendar event via the MCP_Server `get_calendar_event` tool to extract the stated Agenda.
2. IF no agenda is present in the calendar event, THEN THE Analysis_Agent SHALL attempt to infer an agenda from the first 10% of the Transcript by duration.
3. THE Analysis_Agent SHALL represent the Agenda as an ordered list of topic strings, each not exceeding 200 characters.
4. IF the Analysis_Agent cannot extract or infer an agenda, THEN THE Analysis_Report SHALL include an explicit "Agenda: Not Determined" field and the absence SHALL be surfaced in the Analysis_Report.

---

### Requirement 5: Agenda Adherence Analysis `[Stage 1 - Proof of Value]`

**User Story:** As a meeting organizer, I want to know how closely the discussion followed the agenda, so that I can improve future meeting structure.

#### Acceptance Criteria

1. WHEN the Agenda and Transcript are available, THE Analysis_Agent SHALL compute a semantic similarity score between each Agenda topic and the corresponding Transcript segments using text embeddings.
2. THE Analysis_Agent SHALL classify each Agenda topic as "Covered", "Partially Covered", or "Not Covered" based on the similarity score.
3. THE Analysis_Agent SHALL identify Transcript segments that do not correspond to any Agenda topic and classify them as "Off-Agenda Discussion".
4. THE Analysis_Report SHALL include the agenda adherence classification for each topic and a list of off-agenda discussion segments with timestamps.

---

### Requirement 6: Time Allocation Analysis `[Stage 1 - Proof of Value]`

**User Story:** As a meeting organizer, I want to know how much time was spent on each agenda item and on introductory briefing, so that I can evaluate meeting efficiency.

#### Acceptance Criteria

1. THE Analysis_Agent SHALL calculate the time in minutes spent on each Agenda topic based on Transcript segment timestamps.
2. THE Analysis_Agent SHALL identify and measure the duration of meeting preamble (introductions, briefing on agenda) as a distinct time segment.
3. THE Analysis_Report SHALL express time allocation as both absolute minutes and percentage of total meeting duration for each Agenda topic and the preamble segment.
4. IF a meeting duration exceeds 120 minutes, THEN THE Analysis_Agent SHALL flag the meeting as "Extended Duration" in the Analysis_Report.

---

### Requirement 7: Action Item Extraction `[Stage 1 - Proof of Value]`

**User Story:** As a meeting participant, I want the bot to identify and list all action items agreed upon during the meeting, so that I have a clear record of commitments.

#### Acceptance Criteria

1. WHEN the Transcript is finalized, THE Analysis_Agent SHALL extract all Action_Items from the Transcript using the GPT-4o model.
2. Each Action_Item SHALL include: description, owner (Participant name), due date if mentioned, and the Transcript timestamp where it was identified.
3. IF no due date is mentioned for an Action_Item, THEN the due date field SHALL be set to "Not Specified".
4. THE Analysis_Agent SHALL distinguish between proposed action items and confirmed action items based on linguistic markers of agreement in the Transcript.
5. THE Analysis_Report SHALL list Action_Items grouped by owner.

---

### Requirement 8: Participant Agreement Detection `[Stage 3 - Deep Analysis]`

**User Story:** As a meeting organizer, I want to know whether participants agreed on the action items and ideas discussed, so that I can identify unresolved decisions.

#### Acceptance Criteria

1. THE Analysis_Agent SHALL analyze the Transcript for linguistic markers of agreement, disagreement, and ambiguity for each Action_Item and key decision point.
2. THE Analysis_Agent SHALL assign each Action_Item an agreement status of "Agreed", "Disputed", or "Unresolved".
3. THE Analysis_Report SHALL include the agreement status for each Action_Item with supporting Transcript excerpts as evidence.
4. IF an Action_Item is classified as "Disputed" or "Unresolved", THEN THE Analysis_Report SHALL include the names of the Participants who expressed disagreement or ambiguity.

---

### Requirement 9: Participant Sentiment, Tone, and Pitch Analysis `[Stage 3 - Deep Analysis]`

**User Story:** As a meeting organizer, I want to understand the sentiment, tone, and pitch patterns of each participant during the meeting, so that I can identify engagement, confidence, or tension issues beyond what text alone reveals.

#### Acceptance Criteria

1. WHEN the Transcript is finalized, THE Sentiment_Agent SHALL compute a sentiment score for each Participant across their transcript segments.
2. THE Sentiment_Agent SHALL classify each Participant's overall sentiment as "Positive", "Neutral", or "Negative".
3. THE Sentiment_Agent SHALL identify sentiment shifts within a Participant's contributions and record the Transcript timestamp of each shift.
4. THE Analysis_Report SHALL include per-Participant sentiment classification and a timeline of significant sentiment shifts.
5. WHERE a Participant's transcript contribution is fewer than 50 words, THE Sentiment_Agent SHALL classify their sentiment as "Insufficient Data" rather than making a low-confidence classification.
6. WHEN tone and pitch data is available for a Participant, THE Sentiment_Agent SHALL incorporate Tone_Analysis and Pitch_Analysis signals alongside text-based sentiment to produce a combined engagement score.
7. THE Sentiment_Agent SHALL classify each Participant's tone as one of: "Assertive", "Hesitant", "Collaborative", "Neutral", or "Stressed" based on prosody and linguistic features.
8. THE Analysis_Report SHALL include per-Participant tone classification and pitch variation summary alongside the sentiment classification.

---

### Requirement 10: Participation Measurement `[Stage 1 - Proof of Value]`

**User Story:** As a meeting organizer, I want to see how much each participant contributed to the discussion — including audio engagement signals — so that I can identify dominant or disengaged participants.

#### Acceptance Criteria

1. `[Stage 1]` THE Sentiment_Agent SHALL calculate each Participant's speaking time as a percentage of total meeting speaking time.
2. `[Stage 1]` THE Sentiment_Agent SHALL count the number of distinct speaking turns for each Participant.
3. `[Stage 1]` THE Analysis_Report SHALL rank Participants by speaking time percentage in descending order.
4. `[Stage 1]` THE Analysis_Agent SHALL flag any Participant who spoke for less than 2% of total speaking time as "Low Participation".
5. `[Stage 1]` THE Analysis_Agent SHALL flag any Participant who spoke for more than 50% of total speaking time as "Dominant Speaker".
6. `[Stage 3]` WHERE Tone_Analysis and Pitch_Analysis data is available, THE Sentiment_Agent SHALL compute a contribution level score for each Participant that combines speaking time, turn count, and audio engagement signals.
7. `[Stage 3]` THE Analysis_Report SHALL include each Participant's contribution level score alongside their speaking time percentage.

---

### Requirement 11: Participant Relevance Assessment `[Stage 3 - Deep Analysis]`

**User Story:** As a meeting organizer, I want to know whether the right people were in the meeting relative to the agenda, so that I can optimize future invitations.

#### Acceptance Criteria

1. THE Analysis_Agent SHALL retrieve each Participant's display name and, where available, job title from the stored `participant_roster` document (populated by the Bot on meeting join — no additional Graph API call required).
2. THE Analysis_Agent SHALL assess each Participant's relevance to the Agenda topics based on their speaking contributions and the semantic content of those contributions.
3. THE Analysis_Report SHALL classify each Participant as "Highly Relevant", "Relevant", or "Low Relevance" relative to the Agenda.
4. IF a Participant attended but made zero speaking contributions, THE Analysis_Agent SHALL classify them as "Observer" rather than applying a relevance score.

---

### Requirement 12: Real-Time Proactive Insights and Agenda Availability Alert `[Stage 2 - Real-Time Intelligence]`

**User Story:** As a meeting participant, I want the bot to proactively alert the meeting when the agenda is unclear or the discussion goes off-track, so that the team can self-correct in real time rather than discovering issues after the fact.

#### Acceptance Criteria

1. WHILE a meeting is in progress, THE Orchestrator_Agent SHALL continuously evaluate the Transcript against the Agenda at intervals not exceeding 60 seconds.
2. WHEN the Bot joins a meeting, THE Bot SHALL immediately check the calendar invite for an agenda via the MCP_Server `get_calendar_event` tool.
3. IF no agenda is found in the calendar invite, THEN THE Bot SHALL send a Real_Time_Alert to the meeting organizer within 30 seconds of joining, notifying them that no agenda was found and suggesting they share one in the chat.
4. THE missing-agenda Real_Time_Alert SHALL include a suggested agenda template generated from the meeting subject and any available context from the calendar invite.
5. WHEN the first 5 minutes of the meeting have elapsed and no clear agenda has been identified from the Transcript or calendar event, THE Bot SHALL send a Real_Time_Alert to the meeting chat recommending that the organizer clarify the meeting purpose.
6. WHEN the first 8 minutes of the meeting have elapsed and the agenda remains unclear, THE Bot SHALL send a second Real_Time_Alert with a suggested agenda prompt based on the discussion so far.
7. WHEN the Orchestrator_Agent detects that the current discussion topic has deviated from all Agenda items for more than 3 consecutive minutes, THE Bot SHALL send a Real_Time_Alert identifying the off-agenda topic and suggesting a refocus.
8. THE Bot SHALL deliver each Real_Time_Alert via the MCP_Server `send_realtime_alert` tool as an Adaptive Card visible to all consenting Participants in the meeting chat.
9. THE Bot SHALL not send more than one Real_Time_Alert of the same type within any 5-minute window to avoid notification fatigue.
10. IF the Bot is unable to deliver a Real_Time_Alert, THEN THE Bot SHALL log the failure with the meeting ID, alert type, and reason code.

---

### Requirement 13: Real-Time Meeting Cost Tracker `[Stage 2 - Real-Time Intelligence]`

**User Story:** As a meeting organizer, I want to see the estimated dollar value being consumed by the meeting in real time, so that participants are aware of the cost and can make informed decisions about meeting duration and scope.

#### Acceptance Criteria

1. WHEN the Bot joins a meeting, THE Bot SHALL retrieve each Participant's seniority level and hourly rate via the MCP_Server `get_participant_rates` tool.
2. WHILE a meeting is in progress, THE Bot SHALL calculate the Meeting_Cost every 60 seconds as the sum of each Participant's elapsed time multiplied by their hourly rate.
3. THE Bot SHALL display the current Meeting_Cost as an Adaptive Card within the meeting chat, updating the card in place every 60 seconds.
4. THE Meeting_Cost Adaptive Card SHALL display: total estimated cost to date, elapsed meeting time, number of active participants, and a per-participant cost breakdown.
5. IF participant rate data is unavailable for one or more Participants, THEN THE Bot SHALL calculate the Meeting_Cost using available rates and SHALL indicate which Participants are excluded from the calculation.
6. WHEN the meeting ends, THE Bot SHALL include the final Meeting_Cost in the Analysis_Report.
7. THE Bot SHALL store Meeting_Cost snapshots at 5-minute intervals to Azure Cosmos DB for post-meeting review.

---

### Requirement 14: Real-Time Meeting Purpose and Objective Detection `[Stage 2 - Real-Time Intelligence]`

**User Story:** As a meeting participant, I want the bot to identify and display the meeting's purpose and objective at the start, so that everyone is aligned on what the meeting is trying to achieve.

#### Acceptance Criteria

1. WHEN the Bot joins a meeting, THE Orchestrator_Agent SHALL retrieve the calendar event via the MCP_Server `get_calendar_event` tool and analyze the meeting subject and description to form an initial Meeting_Purpose hypothesis.
2. WHEN the first 2 minutes of the meeting have elapsed, THE Orchestrator_Agent SHALL analyze the opening Transcript segments combined with the calendar event context to classify the Meeting_Purpose as one of: "Decision meeting", "Status update", "Brainstorming", "Client presentation", or "Problem-solving".
3. WHEN the Meeting_Purpose is classified, THE Bot SHALL surface it as a Real_Time_Alert Adaptive Card visible to all consenting Participants in the meeting chat.
4. IF the detected Meeting_Purpose conflicts with the calendar invite subject (e.g., invite says "Weekly sync" but discussion signals a client presentation), THEN THE Bot SHALL include a mismatch flag in the Real_Time_Alert card describing the discrepancy.
5. WHILE a meeting is in progress, THE Orchestrator_Agent SHALL evaluate at intervals not exceeding 5 minutes whether the discussion remains aligned with the detected Meeting_Purpose.
6. WHEN the Orchestrator_Agent detects that the discussion has diverged from the detected Meeting_Purpose for more than 5 consecutive minutes, THE Bot SHALL send a Real_Time_Alert noting the divergence.
7. THE Analysis_Report SHALL include the detected Meeting_Purpose, any mismatch flag, and a summary of purpose alignment throughout the meeting.

---

### Requirement 15: Real-Time Voice Pitch, Tone, and Audience Participation Insights `[Stage 2 - Real-Time Intelligence]`

**User Story:** As a meeting organizer, I want real-time visibility into who is participating and how engaged participants are, so that I can actively manage the meeting dynamics.

#### Acceptance Criteria

1. WHILE a meeting is in progress, THE Sentiment_Agent SHALL compute a participation snapshot every 5 minutes containing: list of Participants who have spoken, list of Participants who have not yet spoken, and speaking time distribution across all Participants.
2. WHEN a participation snapshot is computed, THE Bot SHALL update a Participation_Pulse Adaptive Card in the meeting chat displaying: active speakers, silent Participants, a simple engagement indicator per Participant, and an overall meeting energy level of "High", "Medium", or "Low".
3. THE Bot SHALL update the Participation_Pulse card in place (not post a new card) at each 5-minute interval.
4. WHEN a Participant has not spoken for more than 10 consecutive minutes, THE Bot SHALL send a private Real_Time_Alert to the meeting organizer only, suggesting they invite that Participant to contribute.
5. WHILE a meeting is in progress and audio data is available, THE Transcription_Agent SHALL detect significant pitch or tone shifts in real time (e.g., a Participant's voice becomes notably stressed or elevated) and log each detected shift with the Participant identity and Transcript timestamp.
6. THE Bot SHALL NOT send any Real_Time_Alert to the meeting chat for individual pitch or tone shifts — pitch shift data SHALL be logged only for inclusion in the post-meeting Analysis_Report.
7. THE overall meeting energy level displayed on the Participation_Pulse card SHALL be derived from the aggregate of all Participant engagement signals including speaking frequency, turn count, and available audio engagement indicators.
8. IF audio data is unavailable, THE Sentiment_Agent SHALL compute the participation snapshot and energy level from Transcript data alone and SHALL indicate on the Participation_Pulse card that audio signals are not available.

---

### Requirement 16: Real-Time Professional Tone Monitoring `[Stage 2 - Real-Time Intelligence]`

**User Story:** As a meeting organizer, I want the bot to monitor and help maintain a professional tone, especially when external clients or senior executives are present, so that our meetings reflect well on the organization.

#### Acceptance Criteria

1. WHEN the Bot joins a meeting, THE Bot SHALL enrich each Participant's profile with domain (internal vs external) and title from the Graph API, store the result as a `participant_roster` document, and set `is_high_value: true` for any Participant who is external OR holds a C-level/senior title.
2. IF any Participant is identified as external (non-tenant domain) OR holds a C-level or senior title (CEO, CTO, CFO, COO, CPO, CMO, CXO, President, VP, or Director), THEN THE Bot SHALL activate High-Value Participant Mode for the duration of the meeting.
3. WHILE a meeting is in progress, THE Orchestrator_Agent SHALL continuously analyze Transcript segments for Tone_Issues including: aggressive language, dismissive language, interruptions, profanity, and disrespectful tone.
4. THE Orchestrator_Agent SHALL classify each detected Tone_Issue by severity: "Minor" (slightly informal), "Moderate" (unprofessional), or "Severe" (disrespectful or inappropriate).
5. WHILE High-Value Participant Mode is active, THE Orchestrator_Agent SHALL treat "Minor" Tone_Issues as "Moderate" severity for the purpose of alert escalation.
6. WHEN a Tone_Issue of "Moderate" or "Severe" severity is detected, THE Bot SHALL send a private Real_Time_Alert to the meeting organizer only, describing the detected issue, the severity classification, and the Participant who triggered it.
7. WHEN the same Participant triggers a Tone_Issue of the same severity within 3 minutes of a prior private organizer alert, THE Bot SHALL send a professional and constructive Real_Time_Alert to the whole meeting chat (e.g., "Let's keep our discussion focused and respectful to make the most of everyone's time").
8. THE whole-meeting Real_Time_Alert SHALL NOT name the specific Participant or quote the problematic statement — it SHALL be general and constructive in tone.
9. THE Bot SHALL log all detected Tone_Issues with: Transcript timestamp, severity classification, Participant identity, and whether a private alert or whole-meeting alert was sent — regardless of whether any alert was triggered.
10. THE Analysis_Report SHALL include a Professional Tone summary section listing all logged Tone_Issues with timestamps and severity classifications.

---

### Requirement 17: Audio and Video Post-Processing `[Stage 3 - Deep Analysis / Phase 2 - Video]`

**User Story:** As a meeting organizer, I want the bot to perform deep post-call processing of audio and text data for tone and pitch analysis, so that I receive richer insights than text-based analysis alone can provide.

#### Acceptance Criteria

1. `[Stage 3]` WHEN a meeting ends, THE Transcription_Agent SHALL trigger post-processing of the stored audio data using the Azure AI Speech Service batch transcription and prosody analysis APIs.
2. `[Stage 3]` THE Transcription_Agent SHALL extract per-Participant Tone_Analysis and Pitch_Analysis features from the full meeting audio recording.
3. `[Stage 3]` THE Transcription_Agent SHALL correlate audio analysis results with Transcript timestamps and Participant identities and persist the enriched data to Blob Storage.
4. `[Stage 3]` WHEN audio post-processing is complete, THE Transcription_Agent SHALL notify the Orchestrator_Agent so that the Sentiment_Agent can incorporate the enriched signals into the Analysis_Report.
5. `[Stage 3]` IF audio post-processing fails for a Participant, THEN THE Transcription_Agent SHALL log the failure and the Analysis_Report SHALL note that audio analysis is unavailable for that Participant.
6. `[Phase 2]` WHERE video data is available and tenant policy permits, THE Transcription_Agent SHALL store the video recording in Azure Blob Storage (Cool tier) for potential future analysis, without performing video analysis in the MVP.

---

### Requirement 18: Post-Meeting Analysis Report Delivery `[Stage 1 - Proof of Value]`

**User Story:** As a meeting organizer, I want to receive the analysis report in Teams after the meeting ends, so that I can review findings without leaving my workflow.

#### Acceptance Criteria

1. WHEN the Orchestrator_Agent has received completed results from all specialist agents, THE Orchestrator_Agent SHALL compile the Analysis_Report.
2. THE Bot SHALL deliver the Analysis_Report to the meeting organizer via a Teams Adaptive Card in the meeting chat within 10 minutes of the meeting ending.
3. THE Adaptive_Card SHALL present a summary view with expandable sections for: Agenda Adherence, Time Allocation, Action Items, Sentiment Summary, and Participation Summary.
4. THE Bot SHALL also send a condensed Action Items card to all Participants who gave consent.
5. IF report generation exceeds 10 minutes, THEN THE Bot SHALL send a status message to the meeting organizer indicating the delay and an estimated completion time.

---

### Requirement 19: Participant Consent Poll for Analysis Validation `[Stage 3 - Deep Analysis]`

**User Story:** As a meeting participant, I want to confirm or dispute the AI's analysis findings, so that inaccurate conclusions can be flagged before being acted upon.

#### Acceptance Criteria

1. WHEN the Analysis_Report is delivered, THE Bot SHALL send a Poll to all consenting Participants asking them to confirm or dispute the Action_Items and key decisions identified in the report.
2. THE Poll SHALL present each Action_Item individually and allow each Participant to respond: "Confirm", "Dispute", or "Abstain".
3. THE Poll SHALL remain open for 24 hours after delivery.
4. WHEN the Poll closes, THE Bot SHALL update the Analysis_Report with the aggregated Poll responses and re-classify Action_Item agreement status based on Poll results.
5. IF a majority of Participants dispute an Action_Item, THEN THE Bot SHALL mark that Action_Item as "Disputed by Poll" in the final Analysis_Report.
6. THE Bot SHALL notify the meeting organizer when the Poll closes with a summary of responses.

---

### Requirement 20: Transcript and Report Storage `[Stage 1 - Proof of Value]`

**User Story:** As a Teams administrator, I want meeting transcripts and analysis reports stored securely and cost-effectively, so that they can be retrieved for audit or review.

#### Acceptance Criteria

1. THE Transcription_Agent SHALL store raw Transcripts in Azure Blob Storage using the Cool access tier with a container-level retention policy of 90 days by default.
2. THE Analysis_Agent SHALL persist Analysis_Reports to Azure Cosmos DB using the serverless capacity mode.
3. THE Bot SHALL store all data within the tenant's designated Azure region to comply with data residency requirements.
4. WHEN a Participant revokes consent after a meeting, THE Bot SHALL delete that Participant's transcript segments and re-run the analysis within 48 hours, updating the stored Analysis_Report.
5. THE Bot SHALL encrypt all stored Transcripts and Analysis_Reports at rest using Azure-managed keys.

---

### Requirement 21: Orchestrator and A2A Agent Communication `[Stage 1 - Proof of Value]`

**User Story:** As a system operator, I want the agents to communicate reliably using A2A protocol, so that the analysis pipeline is robust and observable.

#### Acceptance Criteria

1. THE Orchestrator_Agent SHALL coordinate the analysis pipeline by dispatching tasks to the Transcription_Agent, Analysis_Agent, and Sentiment_Agent via the Azure AI Foundry A2A protocol.
2. WHEN the Orchestrator_Agent dispatches a task to a specialist agent, THE specialist agent SHALL return a structured JSON response conforming to the agreed task schema.
3. IF a specialist agent fails to respond within 120 seconds, THEN THE Orchestrator_Agent SHALL retry the task once and, if the retry fails, SHALL mark that analysis section as "Unavailable" in the Analysis_Report.
4. THE Orchestrator_Agent SHALL log all A2A task dispatches and responses with timestamps to Azure Monitor.
5. THE MCP_Server SHALL expose all required tools to agents and SHALL return structured error responses for failed tool calls.

---

### Requirement 22: MCP Server Tool Availability `[Stage 1 - Proof of Value / Stage 2 - Real-Time Intelligence / Stage 3 - Deep Analysis]`

**User Story:** As an agent developer, I want a reliable MCP server exposing all required tools, so that agents can access Teams and storage resources without direct SDK dependencies.

#### Acceptance Criteria

1. `[Stage 1]` THE MCP_Server SHALL expose the following core tools: `get_transcript`, `get_calendar_event`, `get_participants`, `post_adaptive_card`, `store_analysis`, `get_analysis`.
   `[Stage 2]` THE MCP_Server SHALL additionally expose: `send_realtime_alert`, `get_participant_rates`, `get_participant_roles`.
   `[Stage 3]` THE MCP_Server SHALL additionally expose: `create_poll`.
2. WHEN an agent calls a MCP_Server tool, THE MCP_Server SHALL respond within 5 seconds under normal operating conditions.
3. IF a MCP_Server tool call fails due to a downstream service error, THEN THE MCP_Server SHALL return a structured error object containing an error code, message, and retryable flag.
4. THE MCP_Server SHALL validate all input parameters against a defined schema before executing any tool and SHALL return a validation error for non-conforming inputs.
5. THE MCP_Server SHALL authenticate all agent requests using Azure AD managed identity tokens.

---

### Requirement 23: Privacy and Compliance `[Stage 1 - Proof of Value]`

**User Story:** As a compliance officer, I want the bot to enforce privacy rules and data handling policies, so that the organization meets its legal obligations.

#### Acceptance Criteria

1. THE Bot SHALL not retain any Transcript data beyond the configured retention period without explicit administrator override.
2. THE Bot SHALL provide a tenant administrator with the ability to configure the default retention period between 30 and 365 days.
3. WHEN a data subject access request is received, THE Bot SHALL be capable of exporting all stored data associated with a specific Participant within 72 hours.
4. THE Bot SHALL not transmit Transcript data outside the configured Azure region boundary.
5. THE Bot SHALL log all data access events to an immutable audit log in Azure Monitor with the accessing identity, timestamp, and resource accessed.

---

### Requirement 24: Historical Analysis Dashboard `[Phase 2]`

**User Story:** As a team leader, I want a web dashboard showing historical meeting analytics across multiple meetings, so that I can identify trends in meeting effectiveness over time.

#### Acceptance Criteria

1. THE Dashboard SHALL display aggregated meeting metrics (average agenda adherence, average cost, participation trends) across a configurable date range.
2. THE Dashboard SHALL allow filtering by participant, team, or meeting type.
3. THE Dashboard SHALL be built using React and Fluent UI v9 and hosted as an Azure Static Web App.
4. THE Dashboard SHALL authenticate users via Azure AD single sign-on.

---

### Requirement 25: Project Management Tool Integration `[Phase 2]`

**User Story:** As a meeting organizer, I want confirmed action items automatically synced to our project management tools, so that I don't have to manually re-enter them.

#### Acceptance Criteria

1. WHEN an Action_Item is confirmed (either by the bot or by Poll), THE Bot SHALL optionally sync it to Microsoft Planner or Jira based on tenant configuration.
2. THE Bot SHALL map Action_Item owner to the corresponding user account in the target project management tool.
3. IF a sync fails, THE Bot SHALL notify the meeting organizer and retain the Action_Item in the Analysis_Report without data loss.

---

### Requirement 26: Video Data Analysis `[Phase 2]`

**User Story:** As a meeting organizer, I want the bot to analyze video data for engagement signals such as facial expressions and attention, so that I get a fuller picture of participant engagement.

#### Acceptance Criteria

1. WHERE video recordings are available and tenant policy permits video analysis, THE Bot SHALL process stored video data using Azure AI Vision or equivalent service.
2. THE Bot SHALL extract per-Participant engagement signals (e.g., attention, expression) and correlate them with Transcript timestamps.
3. THE Analysis_Report SHALL include a video engagement summary per Participant where video analysis data is available.
4. THE Bot SHALL obtain explicit separate consent from Participants before performing video analysis.
