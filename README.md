# ScanSaver — The Negotiator for medical imaging

An MRI in the same city runs anywhere from $400 to $4,000 for the same scan on
the same machine. ScanSaver interviews you once, phones the imaging centers,
extracts real itemized cash prices, negotiates using your best competing quote,
and hands you a ranked report with transcripts and recordings as evidence.

Built on **ElevenLabs Agents** (voice, with Claude as the hosted agent brain) +
**OpenAI** (document parsing, report writing) + **FastAPI/SQLite** (glue) for
the Hack-Nation "The Negotiator" challenge.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys

# terminal 1 — backend + dashboard
uvicorn backend.main:app --reload --port 8000

# terminal 2 — public URL for agent tools & webhooks
ngrok http 8000        # copy https URL into .env as PUBLIC_BASE_URL

# provision all five agents (estimator, caller, 3 counterparties)
python -m scripts.setup_agents

# after intake + confirming a spec at http://localhost:8000 :
python -m scripts.start_call --to +1XXXXXXXXXX --facility "Summit Imaging Center"
python -m scripts.start_call --to +1XXXXXXXXXX --facility "Premier Diagnostic Imaging" --negotiate
```

One-time dashboard steps on elevenlabs.io: import a Twilio number (→
`ELEVENLABS_PHONE_NUMBER_ID`), point the workspace post-call webhook at
`<PUBLIC_BASE_URL>/webhooks/post_call`, and allow the Estimator agent's public
web widget.

## How the agents wire together

The five ElevenLabs agents never talk to each other directly — all orchestration
runs through our FastAPI backend (that's deliberate: the spec, the leverage, and
the evidence chain stay under our control).

```mermaid
flowchart TD
    U([User]) -->|voice widget / phone call| EST["Estimator agent"]
    U -->|doctor's order photo| DOC["parse_document<br/>(OpenAI vision)"]
    EST -->|submit_spec tool| API["FastAPI backend<br/>+ SQLite"]
    DOC --> API
    U -->|confirms spec on dashboard| API
    API -->|"spec injected verbatim; round 2<br/>adds the real best quote as leverage"| CALLER["Caller/Closer agent"]
    CALLER <-->|"phone call (Twilio)"| CP["Receptionists:<br/>stonewaller · lowballer · upseller<br/>(teammates or counterparty agents)"]
    CALLER -->|log_quote / log_outcome tools| API
    API -->|red-flag engine + benchmarks| LEDGER["Dashboard ledger"]
    EL["ElevenLabs post-call webhook"] -->|transcripts + audio| API
    API --> REPORT["Ranked report<br/>+ recordings"]
```

## Repo tour

```
config/            vertical configs — swap file = swap vertical (see moving.example.json)
agents/            prompt templates (<<build-time>> + {{runtime}} tokens)
agents/counterparties/  the simulated market: stonewaller / lowballer / upseller
backend/           FastAPI app, SQLite, red-flag engine, report generator
scripts/           provision agents, launch calls
frontend/          single-file dashboard (intake → confirm → ledger → report)
CLAUDE.md          the real manual — architecture, verify-with-docs list, milestones
```

**Working on this with Claude Code? Start by reading `CLAUDE.md`** — it contains
the docs-verification checklist that must run before the first live call, and
the milestone order.
