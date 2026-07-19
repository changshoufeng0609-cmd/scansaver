"""Point the imported phone number's INBOUND handling at one of our agents.

    python -m scripts.assign_inbound estimator     # default: phone intake
    python -m scripts.assign_inbound upseller      # agent-to-agent rehearsal:
                                                   # now `start_call --to <our own number>`
                                                   # makes the Caller negotiate with Sloane

Outbound calls are unaffected (the Caller is chosen per-call by start_call).
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.elevenlabs_client import BASE, _headers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ids = json.loads((ROOT / "agents" / "agent_ids.json").read_text())
    choices = [k for k in ids if k != "_tools"]
    if len(sys.argv) != 2 or sys.argv[1] not in choices:
        raise SystemExit(f"usage: python -m scripts.assign_inbound <{'|'.join(choices)}>")
    key = sys.argv[1]

    pid = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    if not pid:
        raise SystemExit("ELEVENLABS_PHONE_NUMBER_ID not set in .env")

    r = httpx.patch(f"{BASE}/v1/convai/phone-numbers/{pid}", headers=_headers(),
                    json={"agent_id": ids[key]}, timeout=30)
    r.raise_for_status()
    info = r.json()
    agent = (info.get("assigned_agent") or {}).get("agent_name", ids[key])
    print(f"{info.get('phone_number')} now answered by: {agent}")


if __name__ == "__main__":
    main()
