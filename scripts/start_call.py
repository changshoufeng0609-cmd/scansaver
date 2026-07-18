"""Launch one outbound call with the confirmed spec injected verbatim as
dynamic variables — identically on every call, per the challenge requirements.

Round 1 (gather):
    python -m scripts.start_call --to +15551234567 --facility "Summit Imaging Center"

Round 2 (negotiate, injects the current best quote as leverage):
    python -m scripts.start_call --to +15551234567 --facility "Premier Diagnostic Imaging" --negotiate

For the human-in-the-loop demo, --to is your teammate's real phone; they answer
following one of the agents/counterparties/*.md scripts.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db  # noqa: E402
from backend.elevenlabs_client import outbound_call  # noqa: E402
from backend.report import rank_quotes  # noqa: E402
from backend.spec_utils import (benchmark_line, load_config, payment_line,  # noqa: E402
                                spec_to_job_summary)

ROOT = Path(__file__).resolve().parent.parent


def build_dynamic_variables(spec_id: str, facility: str, negotiate: bool) -> dict:
    config = load_config()
    spec_row = db.get_spec(spec_id)
    if not spec_row:
        raise SystemExit(f"spec {spec_id} not found")
    spec = spec_row["spec"]

    best_quote_line = "You have NO competing quotes yet. Do not negotiate; just gather."
    if negotiate:
        ranked = rank_quotes(spec_id)["ranked"]
        usable = [q for q in ranked if q["high_flags"] == 0 and q["total"]] or ranked
        if not usable:
            raise SystemExit("No quotes in DB yet — run gather calls before --negotiate.")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="E.164 number to dial, e.g. +15551234567")
    ap.add_argument("--facility", required=True, help="Facility name for logging + prompt")
    ap.add_argument("--spec-id", default=None, help="Defaults to latest confirmed spec")
    ap.add_argument("--negotiate", action="store_true",
                    help="Round 2: inject best logged quote as leverage")
    args = ap.parse_args()

    db.init_db()
    spec_id = args.spec_id
    if not spec_id:
        latest = db.latest_spec(confirmed_only=True)
        if not latest:
            raise SystemExit("No confirmed spec. Run intake (voice or document) and confirm first.")
        spec_id = latest["id"]

    agent_ids = json.loads((ROOT / "agents" / "agent_ids.json").read_text())
    phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    if not phone_number_id:
        raise SystemExit("Set ELEVENLABS_PHONE_NUMBER_ID in .env (import a Twilio number first).")

    dyn = build_dynamic_variables(spec_id, args.facility, args.negotiate)
    print("Dynamic variables:\n" + json.dumps(dyn, indent=2))
    result = outbound_call(
        agent_id=agent_ids["caller"],
        agent_phone_number_id=phone_number_id,
        to_number=args.to,
        dynamic_variables=dyn,
    )
    print("Call started:\n" + json.dumps(result, indent=2))
    cid = result.get("conversation_id") or result.get("callSid")
    if cid:
        db.upsert_call(conversation_id=str(cid), spec_id=spec_id,
                       facility_name=args.facility,
                       negotiation_mode=args.negotiate, status="initiated")


if __name__ == "__main__":
    main()
