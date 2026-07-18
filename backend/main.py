"""ScanSaver backend: the webhook target for ElevenLabs agent tools + post-call
events, and the API behind the frontend dashboard.

Run:    uvicorn backend.main:app --reload --port 8000
Expose: ngrok http 8000   -> put the https URL in .env as PUBLIC_BASE_URL
"""
import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

from . import calls, db, elevenlabs_client, redflags, report  # noqa: E402
from .parse_document import parse_document  # noqa: E402
from .spec_utils import get_benchmark, load_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="ScanSaver — The Negotiator for Medical Imaging")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])
db.init_db()


def _agent_ids() -> dict:
    p = ROOT / "agents" / "agent_ids.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _resolve_spec_id(payload_spec_id: str | None) -> str:
    if payload_spec_id:
        return payload_spec_id
    latest = db.latest_spec(confirmed_only=True)
    if not latest:
        raise HTTPException(400, "No confirmed spec exists yet")
    return latest["id"]


# ---------- frontend + config ----------

@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/api/config")
def api_config():
    config = load_config()
    return {
        "vertical": config["vertical"],
        "display_name": config["display_name"],
        "quote_line_items": config["quote_line_items"],
        "counterparty_market": config.get("counterparty_market", []),
        "agent_ids": _agent_ids(),
    }


# ---------- spec lifecycle ----------

@app.post("/api/specs")
async def create_spec(request: Request):
    body = await request.json()
    config = load_config()
    spec_id = db.create_spec(body["spec"], config["vertical"],
                             confirmed=bool(body.get("confirmed")))
    return {"spec_id": spec_id}


@app.post("/api/specs/{spec_id}/confirm")
def confirm_spec(spec_id: str):
    db.confirm_spec(spec_id)
    return {"ok": True}


@app.get("/api/specs/latest")
def latest_spec():
    row = db.latest_spec()
    if not row:
        return JSONResponse({"spec": None})
    return row


@app.post("/api/parse-document")
async def api_parse_document(file: UploadFile):
    config = load_config()
    spec = parse_document(await file.read(), file.filename, config)
    spec_id = db.create_spec(spec, config["vertical"], confirmed=False)
    return {"spec_id": spec_id, "spec": spec}


# ---------- agent server tools (called by ElevenLabs mid-call) ----------

@app.post("/tools/submit_spec")
async def tool_submit_spec(request: Request):
    """Estimator agent submits the verbally-confirmed spec at interview end."""
    body = await request.json()
    config = load_config()
    spec = body.get("spec") or body  # tolerate flat payloads from the LLM
    spec_id = db.create_spec(spec, config["vertical"], confirmed=False)
    return {"spec_id": spec_id,
            "message": "Spec saved. Ask the user to confirm it on screen."}


@app.post("/tools/log_quote")
async def tool_log_quote(request: Request):
    """Caller agent logs an itemized quote mid-call. Can be called again if the
    price moves during negotiation — history is preserved for the report."""
    body = await request.json()
    config = load_config()
    spec_id = _resolve_spec_id(body.get("spec_id"))
    spec_row = db.get_spec(spec_id)
    benchmark = get_benchmark(spec_row["spec"], config)

    total = float(body.get("total") or 0)
    itemized = bool(body.get("itemized", False))
    read_included = bool(body.get("read_included", False))
    flags = redflags.evaluate_quote(total, itemized, read_included, benchmark,
                                    config)
    qid = db.save_quote(
        spec_id=spec_id,
        facility_name=body.get("facility_name", "unknown"),
        line_items=body.get("line_items", []),
        total=total,
        itemized=itemized,
        read_included=read_included,
        notes=body.get("notes", ""),
        red_flags=flags,
    )
    return {"quote_id": qid, "red_flags": [f["label"] for f in flags]}


@app.post("/tools/log_outcome")
async def tool_log_outcome(request: Request):
    """Caller agent's mandatory structured ending for every call."""
    body = await request.json()
    config = load_config()
    spec_id = _resolve_spec_id(body.get("spec_id"))
    outcome_type = body.get("outcome_type", "documented_decline")
    if outcome_type not in config["call_outcomes"]:
        raise HTTPException(400, f"outcome_type must be one of {config['call_outcomes']}")
    flags = redflags.evaluate_outcome(outcome_type, config)
    oid = db.save_outcome(
        spec_id=spec_id,
        facility_name=body.get("facility_name", "unknown"),
        outcome_type=outcome_type,
        details=body.get("details", ""),
        red_flags=flags,
    )
    return {"outcome_id": oid}


# ---------- launch calls from the dashboard ----------

@app.post("/api/calls/start")
async def api_start_call(request: Request):
    """Dashboard button: dial a number as the Caller agent. Same spec-verbatim
    launcher as scripts/start_call.py."""
    body = await request.json()
    to_number = (body.get("to_number") or "").strip()
    facility = (body.get("facility_name") or "").strip()
    if not to_number.startswith("+") or not facility:
        raise HTTPException(400, "to_number (E.164, +1...) and facility_name are required")
    try:
        out = calls.start_call(to_number, facility,
                               negotiate=bool(body.get("negotiate")),
                               spec_id=body.get("spec_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"conversation_id": out["conversation_id"], "spec_id": out["spec_id"]}


# ---------- ElevenLabs post-call webhook ----------

def _verify_signature(raw: bytes, header: str | None) -> bool:
    """HMAC check for post-call webhooks. Verified 2026-07-18 against the
    official SDK (elevenlabs.webhooks.construct_event): header
    'elevenlabs-signature: t=<ts>,v0=<hex hmac_sha256(secret, f"{ts}.{body}")>',
    30-minute timestamp tolerance.
    Skipped (returns True) when ELEVENLABS_WEBHOOK_SECRET is unset — fine for a hackathon over ngrok."""
    secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET")
    if not secret:
        return True
    if not header:
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, sig = parts["t"], parts["v0"]
    except Exception:
        return False
    if abs(time.time() - int(ts)) > 30 * 60:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.{raw.decode()}".encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@app.post("/webhooks/post_call")
async def post_call_webhook(request: Request):
    """Stores transcript + metadata per conversation. Payload shape verified
    2026-07-18: { "type": "post_call_transcription" | "post_call_audio" |
    "call_initiation_failure", "event_timestamp": ..., "data": {...} }.
    Transcription data: conversation_id, status, transcript [{role, message}],
    conversation_initiation_client_data.dynamic_variables.
    Audio data: conversation_id + base64 mp3 in full_audio (nothing else)."""
    raw = await request.body()
    if not _verify_signature(raw, request.headers.get("elevenlabs-signature")):
        raise HTTPException(401, "bad signature")
    body = json.loads(raw)
    data = body.get("data", {})
    cid = data.get("conversation_id")
    if not cid:
        return {"ok": True, "note": "no conversation_id; ignored"}

    if body.get("type") == "post_call_audio":
        dest = ROOT / "data" / "audio" / f"{cid}.mp3"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(data.get("full_audio", "")))
        return {"ok": True, "note": "audio stored"}

    dyn = (data.get("conversation_initiation_client_data") or {}).get(
        "dynamic_variables", {})
    db.upsert_call(
        conversation_id=cid,
        spec_id=dyn.get("spec_id"),
        facility_name=dyn.get("facility_name"),
        negotiation_mode=(dyn.get("negotiation_mode") == "yes"),
        status=data.get("status"),
        transcript=data.get("transcript"),
        raw_webhook=body,
    )
    return {"ok": True}


# ---------- results ----------

@app.get("/api/quotes")
def api_quotes(spec_id: str | None = None):
    sid = _resolve_spec_id(spec_id)
    return {
        "spec_id": sid,
        "quotes": db.list_quotes(sid),
        "outcomes": db.list_outcomes(sid),
        "calls": [
            {k: c[k] for k in ("conversation_id", "facility_name", "status",
                               "negotiation_mode")}
            for c in db.list_calls(sid)
        ],
    }


@app.get("/api/report")
def api_report(spec_id: str | None = None):
    sid = _resolve_spec_id(spec_id)
    return report.generate_report(sid)


@app.get("/api/calls/{conversation_id}/audio")
def call_audio(conversation_id: str):
    dest = ROOT / "data" / "audio" / f"{conversation_id}.mp3"
    if not dest.exists():
        elevenlabs_client.download_audio(conversation_id, dest)
    return FileResponse(dest, media_type="audio/mpeg")
