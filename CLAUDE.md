# CLAUDE.md — ScanSaver (The Negotiator, medical imaging vertical)

Hackathon build for the ElevenLabs "The Negotiator" challenge: a voice-agent
system that interviews a user into a structured job spec, phones imaging
centers for itemized cash prices, negotiates with real leverage, and outputs a
ranked, evidence-backed report. This file is the operating manual — read it
fully before changing code.

## Challenge module → code map

| Brief module | What it demands | Where it lives |
|---|---|---|
| 01 The Estimator | Voice intake + ≥1 document type → same structured spec; user confirms before any calls | `agents/estimator.md`, `backend/parse_document.py`, `/tools/submit_spec` + `/api/specs*` in `backend/main.py`, frontend sections 01–02 |
| 02 The Caller | Calls the market, survives friction, extracts itemized quotes, structured outcome every call | `agents/caller.md`, `scripts/start_call.py`, `/tools/log_quote` + `/tools/log_outcome`, `agents/counterparties/*` |
| 03 The Closer | Negotiates with real leverage; ≥1 call where price measurably moves; ranked report citing transcripts/recordings | negotiation section of `agents/caller.md`, `--negotiate` flag in `start_call.py`, `backend/report.py`, frontend section 04 |
| Cross-cutting | Config-not-code; honesty; red flags | `config/*.json`, `backend/redflags.py`, `backend/spec_utils.py` |

## Golden rules (do not trade these away for demo polish)

1. **Config-not-code.** Anything vertical-specific — questions, schema,
   benchmarks, red-flag rules, levers, the simulated market — lives in
   `config/*.json`. `VERTICAL_CONFIG=config/moving.example.json` must retarget
   the system with zero code edits. If you find yourself hardcoding an
   imaging-specific string in Python or a prompt template, move it to config.
2. **Honesty is a grading criterion.** The agent discloses being an AI when
   asked, never invents details beyond the spec, never fabricates competing
   bids, and ends every call with a structured outcome
   (`itemized_quote` | `callback_commitment` | `documented_decline`). These
   rules are rendered into prompts from `honesty_rules` in config — strengthen
   them, never weaken them.
3. **One spec, verbatim, every call.** Dynamic variables built in
   `scripts/start_call.py` are the only channel for job details. Never let the
   agent improvise the job description.
4. **Real leverage only.** `--negotiate` injects the best *logged* quote from
   the DB. Never seed a fake quote to make the demo look good — the upseller
   counterparty's concession ladder exists precisely so honest leverage
   produces a visible price move.
5. **Red flags per config.** A quote ≥30% below `cash_low` is flagged as
   too-good-to-be-true, matching the brief.

## Architecture

```
voice widget ──► Estimator agent ──submit_spec──► FastAPI ──► SQLite
document ─────► parse_document (OpenAI vision) ──► same spec schema
user confirms spec (frontend 02)
scripts/start_call.py ──► ElevenLabs outbound (Twilio) ──► Caller agent
        │ dynamic vars: spec_id, job_summary, negotiation_mode, best_quote_line
        ▼
   Caller mid-call ──log_quote/log_outcome──► FastAPI ──► red flags ──► ledger UI
   post-call webhook ──► transcripts stored ──► report.py ──► ranked report + audio
```

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill keys

uvicorn backend.main:app --reload --port 8000

python -m scripts.setup_agents  # (re)create all agents; rerun after prompt/config edits
python -m scripts.start_call --to +1XXXXXXXXXX --facility "Summit Imaging Center"
python -m scripts.start_call --to +1XXXXXXXXXX --facility "Premier Diagnostic Imaging" --negotiate
open http://localhost:8000      # dashboard
```

## Environment

| Var | Notes |
|---|---|
| `ELEVENLABS_API_KEY` | required |
| `ELEVENLABS_PHONE_NUMBER_ID` | id of a Twilio number imported in ElevenLabs → Phone Numbers |
| `ELEVENLABS_WEBHOOK_SECRET` | optional; enables HMAC check on `/webhooks/post_call` |
| `ELEVENLABS_LLM` | LLM id string for agents (default `claude-sonnet-4-5`; verified enum also has `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-opus-4-7`) |
| `OPENAI_API_KEY` | for document parsing + report writing |
| `OPENAI_MODEL` | optional; default `gpt-4o` (needs vision + PDF file input) |
| `PUBLIC_BASE_URL` | defaults to `http://localhost:8000`; use a reachable HTTPS URL only for cloud-hosted agent tools/webhooks |
| `VERTICAL_CONFIG` | default `config/medical_imaging.json` |

## Verify with live docs — DO THIS FIRST

> **Status: verification pass completed 2026-07-18.** Docs moved to the
> `/docs/eleven-agents/` namespace. Main drift found and fixed: agent tools are
> now workspace resources (`POST /v1/convai/tools` → reference via
> `prompt.tool_ids`); inline `prompt.tools` no longer exists. Items 1–6 fixed
> in place; item 7 (voice ids) is checked at `setup_agents` runtime against
> `GET /v1/voices`. Re-run this list if the API misbehaves later.

The ElevenLabs API moves fast; the scaffold marks every assumption with
`VERIFY`. Docs are agent-friendly: append `.md` to any docs URL for markdown,
or `/llms.txt` for an index — start at `https://elevenlabs.io/docs/llms.txt`.
Check, and fix in place if drifted:

1. Agent create payload + LLM id strings → `backend/elevenlabs_client.py::create_agent`, `scripts/setup_agents.py::DEFAULT_LLM`
2. Webhook/server-tool schema (inline vs workspace tool resources) → `elevenlabs_client.py::webhook_tool`
3. Outbound call endpoint + field names → `elevenlabs_client.py::outbound_call`
4. Post-call webhook payload shape + signature header format → `backend/main.py::post_call_webhook`, `_verify_signature`
5. Conversation audio endpoint → `elevenlabs_client.py::download_audio`
6. Widget embed tag + script URL, and making the estimator widget public → `frontend/index.html::loadConfig`
7. Voice ids in `setup_agents.py::VOICES` exist in the workspace

## Milestones (build in this order)

- **M0** — env sanity: `uvicorn` up, `GET /api/config` returns config. ✓ when dashboard loads.
- **M1** — docs verification pass (list above), fix any drift. ✓ when `setup_agents.py` runs clean and ids land in `agents/agent_ids.json`.
- **M2** — Estimator end-to-end in the widget: interview → verbal confirm → `submit_spec` → spec appears via "Load latest" → confirm in UI. 
- **M3** — Document path: upload a sample order/bill photo → same schema → confirm. (Both intake paths must produce identical structure — brief requirement.)
- **M4** — First outbound call to your own phone; you ad-lib a receptionist; quote lands in the ledger with red flags computed; post-call webhook stores the transcript.
- **M5** — Full market round: 3 calls vs the three counterparty scripts (teammate role-plays, or agent-to-agent — see demo runbook). All three structured outcome types exercised.
- **M6** — Negotiation round: `--negotiate` vs the upseller; price moves on-call; second `log_quote` recorded; "price moved" badge shows.
- **M7** — Report: ranked list, plain-language recommendation citing ≥1 verbatim transcript line, audio playback working.
- **M8** — Benchmarks made real: replace example numbers in config with CMS Physician Fee Schedule / FAIR Health / hospital transparency data for the demo ZIP; note sources in the config `_warning` field.

## Demo runbook (recommended shape)

- **Counterparties:** simplest reliable rig is human-in-the-loop — the Caller
  dials teammates' real phones via Twilio; each teammate performs one
  `agents/counterparties/*.md` script (they double as role-play scripts).
  Agent-to-agent works too: assign counterparty agents to a second inbound
  number and have the Caller dial it — but rehearse latency and turn-taking.
- **The money moment:** round 1 gathers three quotes (stonewaller → callback
  commitment; lowballer → teaser exposed by itemization questions; upseller →
  $950). Round 2 `--negotiate` on the upseller: agent cites the real best quote,
  Sloane's ladder concedes to ~$725, dashboard shows the strike-through. That
  is the brief's "price changes mid-call due to leverage" proof.
- **Also show:** AI-disclosure moment (have a role-player ask "is this a
  robot?"), a red-flag stamp on the lowballer, config swap slide
  (`moving.example.json`), report with audio.
- **Never** cold-call real clinics in volume for the demo; if you want one real
  call, one consenting real facility is plenty.

## Conventions

- Python 3.11+, FastAPI, no ORM; JSON blobs in SQLite (`backend/db.py`).
- Prompts are markdown templates: `<<TOKEN>>` = build-time (filled from config
  by `setup_agents.py`), `{{token}}` = ElevenLabs runtime dynamic variable.
  `setup_agents.py` fails loudly on unfilled `<<…>>`.
- Keep new vertical logic out of `.py` files — extend the config schema instead,
  then teach `spec_utils.py`/`redflags.py` to interpret the new *shape* generically.
```
