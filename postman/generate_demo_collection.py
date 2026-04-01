"""
Generates postman/Meeting Analyzer - Demo.postman_collection.json

Scenario: Q3 Product Roadmap Planning — 60-minute meeting
Participants:
  sarah-pm    Sarah Chen      Product Manager (organiser)
  james-eng   James Okafor    Engineering Lead
  priya-des   Priya Sharma    Design Lead
  tom-data    Tom Reyes       Data & Analytics

Agenda:
  1. Q3 Feature Prioritisation
  2. Technical Feasibility Review
  3. Design & UX Alignment
  (+ one off-agenda tangent: team offsite planning)

Run: python postman/generate_demo_collection.py
"""
import json
from pathlib import Path

MID = "mtg-roadmap-q3"
BOT_ID = "bot-1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post(name, url, body, tests=None, seq=None):
    item = {
        "name": name,
        "request": {
            "method": "POST",
            "url": url,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": {"mode": "raw", "raw": json.dumps(body, indent=2),
                     "options": {"raw": {"language": "json"}}},
        },
    }
    if tests:
        item["event"] = [{"listen": "test", "script": {
            "type": "text/javascript", "exec": tests}}]
    return item


def status_test(code):
    return [f"pm.test('Status {code}', () => pm.response.to.have.status({code}));"]


def json_test(code, *checks):
    lines = [f"pm.test('Status {code}', () => pm.response.to.have.status({code}));",
             "const b = pm.response.json();"]
    lines += [f"pm.test('{c[0]}', () => {c[1]});" for c in checks]
    return lines


# ---------------------------------------------------------------------------
# Transcript — 20 segments, multi-turn conversation
# ---------------------------------------------------------------------------

SEGMENTS = [
    # Preamble / joining
    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:00:00Z", "2026-07-15T09:00:22Z", 22,
     "Good morning everyone. Let's get started — we have a lot to cover today. "
     "The goal is to lock down our Q3 roadmap priorities and make sure engineering and design are aligned before we go to stakeholders on Friday."),

    ("james-eng", "James Okafor", "2026-07-15T09:00:25Z", "2026-07-15T09:00:38Z", 13,
     "Morning Sarah. I've reviewed the backlog items. Ready when you are."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:00:40Z", "2026-07-15T09:00:52Z", 12,
     "Hi all. I've got the design concepts ready to walk through for the top three features."),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:00:54Z", "2026-07-15T09:01:10Z", 16,
     "Morning. I pulled the usage data from last quarter — it should help us prioritise. "
     "I'll share my screen when we get to that section."),

    # Agenda item 1: Q3 Feature Prioritisation
    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:01:15Z", "2026-07-15T09:02:10Z", 55,
     "Okay, first item — Q3 feature prioritisation. Based on customer feedback and the OKRs, "
     "I'm proposing we focus on three things: the real-time collaboration module, the analytics dashboard redesign, "
     "and the mobile offline mode. Tom, can you walk us through the usage data to validate these?"),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:02:15Z", "2026-07-15T09:03:45Z", 90,
     "Sure. So looking at Q2 data — the collaboration features had a 34% drop-off rate at the point where users "
     "try to co-edit. That's our biggest pain point. The analytics dashboard has a 12% weekly active usage rate "
     "which is low for a core feature — users are telling us it's too complex. "
     "Mobile offline mode is requested by 67% of our enterprise customers in the last NPS survey. "
     "So all three of Sarah's picks are data-backed."),

    ("james-eng", "James Okafor", "2026-07-15T09:03:50Z", "2026-07-15T09:05:00Z", 70,
     "The collaboration module is the most complex technically. We're talking about operational transformation "
     "or CRDT-based conflict resolution — that's a significant architecture change. "
     "I'd estimate 8 to 10 weeks for a solid implementation. "
     "The analytics dashboard is more straightforward — maybe 4 weeks if we scope it right. "
     "Mobile offline is somewhere in between, around 6 weeks, but it has dependencies on the sync service."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:05:05Z", "2026-07-15T09:06:00Z", 55,
     "From a design perspective, the analytics dashboard is actually the most ready — "
     "I have high-fidelity mockups done. The collaboration module needs a full UX rethink "
     "because the current mental model is confusing. I'd need at least 3 weeks of design work before "
     "engineering can start on that one."),

    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:06:05Z", "2026-07-15T09:06:50Z", 45,
     "So it sounds like the analytics dashboard is our quick win — design is ready, engineering estimate is manageable. "
     "I'd like to propose we make that our P1 for Q3, start the collaboration module design sprint in parallel, "
     "and push mobile offline to Q4 unless we can find a way to reduce the scope. Does anyone disagree?"),

    ("james-eng", "James Okafor", "2026-07-15T09:06:55Z", "2026-07-15T09:07:30Z", 35,
     "I'd push back slightly on pushing mobile offline to Q4. We have three enterprise contracts "
     "that are contingent on that feature. Losing those deals would hurt more than the engineering cost. "
     "Can we do a reduced scope — read-only offline mode first?"),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:07:35Z", "2026-07-15T09:07:55Z", 20,
     "The enterprise customers specifically asked for read-write offline. Read-only might not satisfy the contract terms."),

    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:08:00Z", "2026-07-15T09:08:40Z", 40,
     "Okay, let's keep mobile offline in Q3 but descope to the most critical user flows. "
     "James, can you work with the enterprise team to define the minimum viable offline scope by end of week? "
     "That becomes an action item."),

    ("james-eng", "James Okafor", "2026-07-15T09:08:45Z", "2026-07-15T09:08:55Z", 10,
     "Agreed. I'll set up a call with Marcus from enterprise sales tomorrow."),

    # Agenda item 2: Technical Feasibility Review
    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:09:00Z", "2026-07-15T09:09:20Z", 20,
     "Good. Moving to item two — technical feasibility. James, you flagged some infrastructure concerns in the pre-read."),

    ("james-eng", "James Okafor", "2026-07-15T09:09:25Z", "2026-07-15T09:11:00Z", 95,
     "Yes. The main concern is our current WebSocket infrastructure won't scale to support real-time collaboration "
     "for our enterprise tier — we're talking about rooms with up to 200 concurrent editors. "
     "We'd need to migrate to a dedicated presence service, probably using Redis pub-sub. "
     "That's not in the current Q3 budget. I've drafted a proposal for a phased approach — "
     "start with a 20-user limit in Q3, scale in Q4 once we've secured the infrastructure budget. "
     "I've shared the doc in the channel."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:11:05Z", "2026-07-15T09:11:45Z", 40,
     "The 20-user limit is actually fine for our initial target segment — SMBs. "
     "Enterprise collaboration is a Q4 story anyway based on our go-to-market plan. "
     "I think the phased approach makes sense."),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:11:50Z", "2026-07-15T09:12:20Z", 30,
     "Agreed. And honestly 80% of our active collaboration sessions have fewer than 10 participants. "
     "The 20-user cap covers the vast majority of real usage."),

    # Off-agenda tangent
    ("james-eng", "James Okafor", "2026-07-15T09:12:25Z", "2026-07-15T09:12:55Z", 30,
     "Quick side note — has anyone heard anything about the team offsite? "
     "I know it's off-topic but people keep asking me and I don't have an answer."),

    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:13:00Z", "2026-07-15T09:13:20Z", 20,
     "Let's park that — I'll send a separate note. Back to the roadmap."),

    # Agenda item 3: Design & UX Alignment
    ("priya-des", "Priya Sharma", "2026-07-15T09:13:25Z", "2026-07-15T09:15:00Z", 95,
     "For the analytics dashboard redesign, I want to walk through the three core changes. "
     "First, we're replacing the current widget-based layout with a guided insights view — "
     "the data shows users don't know where to start. Second, we're adding a natural language query bar "
     "so users can ask questions like 'show me churn by region last month'. "
     "Third, we're introducing saved views so teams can share their dashboards. "
     "Tom, I'd love your input on the NLQ feature — is the data model ready to support that?"),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:15:05Z", "2026-07-15T09:16:00Z", 55,
     "The data model can support it but we'd need to build a query translation layer. "
     "I'd estimate 2 weeks of data engineering work. The risk is accuracy — "
     "NLQ on complex metrics can give misleading results if the translation is off. "
     "I'd recommend we scope it to a fixed set of supported query patterns for V1 "
     "rather than open-ended natural language."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:16:05Z", "2026-07-15T09:16:40Z", 35,
     "That's a fair constraint. I can design around a curated query library — "
     "maybe 20 to 30 common patterns. That actually makes the UX cleaner too."),

    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:16:45Z", "2026-07-15T09:17:30Z", 45,
     "I love that direction. Priya, can you put together a list of the top 25 query patterns "
     "based on what customers actually ask in support tickets? Tom can validate them against the data model. "
     "Let's make that an action item with a deadline of next Wednesday."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:17:35Z", "2026-07-15T09:17:45Z", 10,
     "Will do. I'll pull the support ticket analysis and have a draft by Tuesday so Tom has time to review."),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:17:50Z", "2026-07-15T09:18:00Z", 10,
     "Works for me."),

    # Wrap-up
    ("sarah-pm",  "Sarah Chen",   "2026-07-15T09:18:05Z", "2026-07-15T09:19:00Z", 55,
     "Great. Let me summarise the decisions and action items. "
     "Decisions: analytics dashboard is P1 for Q3, collaboration module starts with design sprint this sprint, "
     "mobile offline stays in Q3 with reduced scope, phased infrastructure approach approved for collaboration. "
     "Action items: James to define minimum viable offline scope with enterprise team by Friday, "
     "Priya to draft top 25 NLQ patterns by Tuesday, Tom to validate query patterns against data model by Wednesday. "
     "Any final questions?"),

    ("james-eng", "James Okafor", "2026-07-15T09:19:05Z", "2026-07-15T09:19:15Z", 10,
     "No, that's clear. Thanks Sarah."),

    ("priya-des", "Priya Sharma", "2026-07-15T09:19:17Z", "2026-07-15T09:19:25Z", 8,
     "All good. Thanks everyone."),

    ("tom-data",  "Tom Reyes",    "2026-07-15T09:19:27Z", "2026-07-15T09:19:35Z", 8,
     "Thanks. Talk soon."),
]

AGENDA = [
    "Q3 Feature Prioritisation",
    "Technical Feasibility Review",
    "Design and UX Alignment",
]

PARTICIPANTS = {
    "sarah-pm":  "Sarah Chen",
    "james-eng": "James Okafor",
    "priya-des": "Priya Sharma",
    "tom-data":  "Tom Reyes",
}

# ---------------------------------------------------------------------------
# Build collection items
# ---------------------------------------------------------------------------

def phase1_start_meeting():
    body = {
        "type": "conversationUpdate",
        "id": "activity-001",
        "timestamp": "2026-07-15T08:59:00Z",
        "channelId": "msteams",
        "from": {"id": "sarah-pm", "name": "Sarah Chen"},
        "recipient": {"id": BOT_ID, "name": "MeetingBot"},
        "conversation": {"id": MID},
        "membersAdded": [
            {"id": BOT_ID, "name": "MeetingBot"},
            {"id": "sarah-pm", "name": "Sarah Chen"},
            {"id": "james-eng", "name": "James Okafor"},
            {"id": "priya-des", "name": "Priya Sharma"},
            {"id": "tom-data", "name": "Tom Reyes"},
        ],
        "membersRemoved": [],
        "channelData": {
            "meeting": {"id": MID},
            "participants": [
                {"id": "sarah-pm",  "name": "Sarah Chen",   "tenantId": "t-1", "role": "organizer"},
                {"id": "james-eng", "name": "James Okafor", "tenantId": "t-1", "role": "presenter"},
                {"id": "priya-des", "name": "Priya Sharma", "tenantId": "t-1", "role": "attendee"},
                {"id": "tom-data",  "name": "Tom Reyes",    "tenantId": "t-1", "role": "attendee"},
            ],
        },
    }
    return post("01 - Bot Joins Meeting", "{{bot_url}}/api/messages", body,
                tests=status_test(201))


def phase2_store_meeting():
    body = {
        "meeting_record": {
            "id": f"meeting_{MID}",
            "type": "meeting",
            "meeting_id": MID,
            "organizer_id": "sarah-pm",
            "organizer_name": "Sarah Chen",
            "subject": "Q3 Product Roadmap Planning",
            "start_time": "2026-07-15T09:00:00Z",
            "end_time": "2026-07-15T10:00:00Z",
            "duration_minutes": 60.0,
            "participants": list(PARTICIPANTS.keys()),
            "stage": "transcribing",
            "created_at": "2026-07-15T08:55:00Z",
            "updated_at": "2026-07-15T08:55:00Z",
            "azure_region": "eastus",
            "retention_expires_at": "2026-10-15T00:00:00Z",
            "recording_enabled": False,
        }
    }
    return post("02 - Store Meeting Record", "{{mcp_url}}/v1/tools/meeting/store_meeting_record",
                body, tests=status_test(204))


def phase3_consent():
    items = []
    for i, (pid, name) in enumerate(PARTICIPANTS.items()):
        body = {
            "consent_record": {
                "id": f"consent_{MID}_{pid}",
                "type": "consent",
                "meeting_id": MID,
                "participant_id": pid,
                "participant_name": name,
                "decision": "granted",
                "timestamp": f"2026-07-15T09:00:{10 + i * 5:02d}Z",
            }
        }
        items.append(post(
            f"0{3 + i} - Consent Granted: {name}",
            "{{mcp_url}}/v1/tools/consent/store_consent_record",
            body, tests=status_test(204)
        ))
    return items


def phase4_transcript():
    items = []
    for seq, (pid, name, start, end, dur, text) in enumerate(SEGMENTS, start=1):
        body = {
            "segment": {
                "id": f"seg_{MID}_{seq}",
                "type": "transcript_segment",
                "meeting_id": MID,
                "sequence": seq,
                "participant_id": pid,
                "participant_name": name,
                "text": text,
                "start_time": start,
                "end_time": end,
                "duration_seconds": float(dur),
                "consent_verified": True,
            }
        }
        short = text[:60] + "..." if len(text) > 60 else text
        items.append(post(
            f"Seg {seq:02d} [{name}]: {short}",
            "{{mcp_url}}/v1/tools/transcript/store_transcript_segment",
            body, tests=status_test(204)
        ))
    return items


def phase5_realtime():
    items = []

    # Similarity check against agenda mid-meeting
    full_text = " ".join(s[5] for s in SEGMENTS[:15])
    items.append(post(
        "Similarity Check - Mid Meeting",
        "{{mcp_url}}/v1/tools/similarity/compute_similarity",
        {"text": full_text[:2000], "agenda_topics": AGENDA, "meeting_id": MID},
        tests=json_test(200,
            ("scores length matches agenda", "pm.expect(b.scores).to.have.lengthOf(3)"),
            ("max_score in range", "pm.expect(b.max_score).to.be.within(0, 1)"),
        )
    ))

    # Cost snapshots at 15, 30, 45 min
    for i, (elapsed, cost) in enumerate([(15, 125.0), (30, 250.0), (45, 375.0)]):
        items.append(post(
            f"Cost Snapshot - {elapsed} min",
            "{{mcp_url}}/v1/tools/realtime/store_cost_snapshot",
            {"snapshot": {
                "id": f"cost_{MID}_{i}",
                "type": "cost_snapshot",
                "meeting_id": MID,
                "snapshot_index": i,
                "captured_at": f"2026-07-15T09:{elapsed:02d}:00Z",
                "elapsed_minutes": float(elapsed),
                "active_participant_count": 4,
                "total_cost": cost,
                "currency": "USD",
                "per_participant": [
                    {"participant_id": "sarah-pm",  "participant_name": "Sarah Chen",   "hourly_rate": 150.0, "elapsed_cost": cost * 0.3},
                    {"participant_id": "james-eng", "participant_name": "James Okafor", "hourly_rate": 175.0, "elapsed_cost": cost * 0.3},
                    {"participant_id": "priya-des", "participant_name": "Priya Sharma", "hourly_rate": 140.0, "elapsed_cost": cost * 0.2},
                    {"participant_id": "tom-data",  "participant_name": "Tom Reyes",    "hourly_rate": 130.0, "elapsed_cost": cost * 0.2},
                ],
            }},
            tests=status_test(204)
        ))

    # Realtime alert — off-track detected (off-agenda tangent)
    items.append(post(
        "Realtime Alert - Off Track (offsite tangent)",
        "{{mcp_url}}/v1/tools/realtime/send_realtime_alert",
        {
            "meeting_id": MID,
            "alert_type": "off_track",
            "card_payload": {
                "type": "off_track",
                "meeting_id": MID,
                "message": "Discussion appears to have moved off agenda",
                "max_similarity": 0.08,
            },
        },
        tests=status_test(204)
    ))

    return items


def phase6_end_meeting():
    body = {
        "type": "conversationUpdate",
        "id": "activity-002",
        "timestamp": "2026-07-15T09:20:00Z",
        "channelId": "msteams",
        "from": {"id": "sarah-pm", "name": "Sarah Chen"},
        "recipient": {"id": BOT_ID, "name": "MeetingBot"},
        "conversation": {"id": MID},
        "membersAdded": [],
        "membersRemoved": [{"id": BOT_ID, "name": "MeetingBot"}],
        "channelData": {"meeting": {"id": MID}},
    }
    return post("Bot Leaves Meeting - Triggers Analysis Pipeline",
                "{{bot_url}}/api/messages", body,
                tests=status_test(201))


def phase7_verify():
    items = []
    items.append(post(
        "Get Analysis Report",
        "{{mcp_url}}/v1/tools/analysis/get_analysis_report",
        {"meeting_id": MID},
        tests=json_test(200,
            ("meeting_id matches", f"pm.expect(b.meeting_id).to.eql('{MID}')"),
            ("agenda present", "pm.expect(b.agenda).to.be.an('array')"),
            ("generated_at set", "pm.expect(b.generated_at).to.be.a('string').and.not.empty"),
        )
    ))
    return items


def phase8_poll():
    body = {
        "meeting_id": MID,
        "action_items": [
            {
                "id": f"action_{MID}_1",
                "type": "action_item",
                "meeting_id": MID,
                "sequence": 1,
                "description": "Define minimum viable offline scope with enterprise team",
                "owner_participant_id": "james-eng",
                "owner_name": "James Okafor",
                "due_date": "2026-07-18",
                "transcript_timestamp": "2026-07-15T09:08:00Z",
                "status": "Confirmed",
            },
            {
                "id": f"action_{MID}_2",
                "type": "action_item",
                "meeting_id": MID,
                "sequence": 2,
                "description": "Draft top 25 NLQ query patterns from support tickets",
                "owner_participant_id": "priya-des",
                "owner_name": "Priya Sharma",
                "due_date": "2026-07-22",
                "transcript_timestamp": "2026-07-15T09:16:45Z",
                "status": "Confirmed",
            },
            {
                "id": f"action_{MID}_3",
                "type": "action_item",
                "meeting_id": MID,
                "sequence": 3,
                "description": "Validate NLQ query patterns against data model",
                "owner_participant_id": "tom-data",
                "owner_name": "Tom Reyes",
                "due_date": "2026-07-23",
                "transcript_timestamp": "2026-07-15T09:16:45Z",
                "status": "Proposed",
            },
        ],
    }
    return post("Create Action Item Poll",
                "{{mcp_url}}/v1/tools/poll/create_poll", body,
                tests=json_test(200,
                    ("poll_id returned", "pm.expect(b.poll_id).to.be.a('string').and.not.empty"),
                ))


# ---------------------------------------------------------------------------
# Assemble collection
# ---------------------------------------------------------------------------

consent_items = phase3_consent()
transcript_items = phase4_transcript()
realtime_items = phase5_realtime()

collection = {
    "info": {
        "name": "Meeting Analyzer - Demo",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        "description": (
            "Full meeting scenario: Q3 Product Roadmap Planning (60 min, 4 participants). "
            "Run via Collection Runner in sequence. Requires ORCH_FOUNDRY_MODE=local (OpenAI) "
            "or ORCH_FOUNDRY_MODE=mock for canned responses."
        ),
    },
    "variable": [
        {"key": "mcp_url", "value": "http://localhost:8000"},
        {"key": "bot_url", "value": "http://localhost:3978"},
    ],
    "item": [
        {
            "name": "Phase 1 - Start Meeting",
            "item": [phase1_start_meeting()],
        },
        {
            "name": "Phase 2 - Store Meeting Record",
            "item": [phase2_store_meeting()],
        },
        {
            "name": "Phase 3 - Consent (all 4 participants)",
            "item": consent_items,
        },
        {
            "name": "Phase 4 - Transcript (28 segments)",
            "item": transcript_items,
        },
        {
            "name": "Phase 5 - Realtime Monitoring",
            "item": realtime_items,
        },
        {
            "name": "Phase 6 - End Meeting",
            "item": [phase6_end_meeting()],
        },
        {
            "name": "Phase 7 - Verify Analysis Report",
            "item": phase7_verify(),
        },
        {
            "name": "Phase 8 - Action Item Poll",
            "item": [phase8_poll()],
        },
    ],
}

out = Path(__file__).parent / "Meeting Analyzer - Demo.postman_collection.json"
out.write_text(json.dumps(collection, indent=2))
print(f"Written: {out}")
print(f"  Phases: {len(collection['item'])}")
print(f"  Transcript segments: {len(transcript_items)}")
print(f"  Total requests: {sum(len(f['item']) for f in collection['item'])}")
