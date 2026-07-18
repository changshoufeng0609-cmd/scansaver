"""Launch one outbound call with the confirmed spec injected verbatim as
dynamic variables — identically on every call, per the challenge requirements.

Round 1 (gather):
    python -m scripts.start_call --to +15551234567 --facility "Summit Imaging Center"

Round 2 (negotiate, injects the current best quote as leverage):
    python -m scripts.start_call --to +15551234567 --facility "Premier Diagnostic Imaging" --negotiate

For the human-in-the-loop demo, --to is your teammate's real phone; they answer
following one of the agents/counterparties/*.md scripts.

The same launcher is exposed to the dashboard as POST /api/calls/start
(backend/calls.py holds the shared logic).
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import calls, db  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="E.164 number to dial, e.g. +15551234567")
    ap.add_argument("--facility", required=True, help="Facility name for logging + prompt")
    ap.add_argument("--spec-id", default=None, help="Defaults to latest confirmed spec")
    ap.add_argument("--negotiate", action="store_true",
                    help="Round 2: inject best logged quote as leverage")
    args = ap.parse_args()

    db.init_db()
    try:
        out = calls.start_call(args.to, args.facility, args.negotiate, args.spec_id)
    except ValueError as e:
        raise SystemExit(str(e))
    print("Dynamic variables:\n" + json.dumps(out["dynamic_variables"], indent=2))
    print("Call started:\n" + json.dumps(out["result"], indent=2))


if __name__ == "__main__":
    main()
