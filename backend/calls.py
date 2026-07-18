"""Shared outbound-call launcher: builds the dynamic variables from a confirmed
spec (verbatim, identically on every call) and starts the call. Used by both
scripts/start_call.py (CLI) and the dashboard's POST /api/calls/start."""
import json
import os
from pathlib import Path

from . import db
from .elevenlabs_client import outbound_call
from .report import rank_quotes
from .spec_utils import (benchmark_line, load_config, payment_line,
                         spec_to_job_summary)

ROOT = Path(__file__).resolve().parent.parent


def build_dynamic_variables(spec_id: str, facility: str, negotiate: bool) -> dict:
    config = load_config()
    spec_row = db.get_spec(spec_id)
    if not spec_row:
        raise ValueError(f"spec {spec_id} not found")
    spec = spec_row["spec"]

    best_quote_line = "You have NO competing quotes yet. Do not negotiate; just gather."
    if negotiate:
        ranked = rank_quotes(spec_id)["ranked"]
        usable = [q for q in ranked if q["high_flags"] == 0 and q["total"]] or ranked
        if not usable:
            raise ValueError("No quotes in DB yet — run gather calls before negotiating.")
        best = usable[0]
        best_quote_line = (
            f"Your real, logged competing quote: ${best['total']:.0f} "
            f"({'itemized' if best['itemized'] else 'not itemized'}) from "
            f"{best['facility_name']}. This is genuine leverage — you may cite "
            f"the amount; do not name the other facility unless asked."
        )

    return {
        "spec_id": spec_id,
        "facility_name": facility,
        "job_summary": spec_to_job_summary(spec, config),
        "payment_line": payment_line(spec),
        "negotiation_mode": "yes" if negotiate else "no",
        "best_quote_line": best_quote_line,
        "benchmark_line": benchmark_line(spec, config),
    }


def start_call(to_number: str, facility: str, negotiate: bool = False,
               spec_id: str | None = None) -> dict:
    """Launch one outbound call; returns {conversation_id, dynamic_variables}."""
    if not spec_id:
        latest = db.latest_spec(confirmed_only=True)
        if not latest:
            raise ValueError("No confirmed spec. Run intake (voice or document) and confirm first.")
        spec_id = latest["id"]

    agent_ids = json.loads((ROOT / "agents" / "agent_ids.json").read_text())
    phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    if not phone_number_id:
        raise ValueError("Set ELEVENLABS_PHONE_NUMBER_ID in .env (import a Twilio number first).")

    dyn = build_dynamic_variables(spec_id, facility, negotiate)
    result = outbound_call(
        agent_id=agent_ids["caller"],
        agent_phone_number_id=phone_number_id,
        to_number=to_number,
        dynamic_variables=dyn,
    )
    cid = result.get("conversation_id") or result.get("callSid")
    if cid:
        db.upsert_call(conversation_id=str(cid), spec_id=spec_id,
                       facility_name=facility,
                       negotiation_mode=negotiate, status="initiated")
    return {"conversation_id": cid, "result": result, "dynamic_variables": dyn,
            "spec_id": spec_id}
