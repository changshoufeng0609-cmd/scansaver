"""Autopilot: one phone call in → every facility called → one negotiation
round → done. Triggered when the Estimator submits a verbally-confirmed spec
while the dashboard's autopilot toggle is on (default: off).

The verbal confirmation IS the user confirmation the brief requires — the
Estimator's prompt forbids submit_spec before an explicit yes. The dashboard
confirm button remains as the manual path.

Facility numbers come from config (counterparty_market[].phone). For solo
rehearsal set AUTOPILOT_PHONE_OVERRIDE in .env to route every facility call
to one phone. Facilities without a number are skipped — autopilot never
invents a dial target.
"""
import json
import os
import threading
import time
from pathlib import Path

from . import calls, elevenlabs_client
from .report import rank_quotes
from .spec_utils import load_config

# Enabled by default: the product promise is "one phone call in, ranked report
# out, zero clicks". Flip the dashboard toggle off while developing/testing so
# a stray intake doesn't dial the whole market.
STATE = {"enabled": True, "running": False, "log": []}


def _log(msg: str):
    STATE["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    del STATE["log"][:-40]


def _phone(cp: dict) -> str:
    """Dial-target resolution: env override > gitignored local map > config.
    Personal numbers live in config/phones.local.json so they never reach git."""
    override = os.environ.get("AUTOPILOT_PHONE_OVERRIDE")
    if override:
        return override
    local = Path(__file__).resolve().parent.parent / "config" / "phones.local.json"
    if local.exists():
        try:
            mapped = json.loads(local.read_text()).get(cp.get("agent_key", ""))
            if mapped:
                return mapped
        except Exception:
            pass
    return cp.get("phone") or ""


def _wait_done(conversation_id: str, timeout: int = 420) -> str:
    start = time.time()
    while time.time() - start < timeout:
        try:
            d = elevenlabs_client.get_conversation(conversation_id)
            if d.get("status") in ("done", "failed"):
                return d.get("status")
        except Exception:
            pass
        time.sleep(5)
    return "timeout"


def _run(spec_id: str):
    config = load_config()
    market = [cp for cp in config.get("counterparty_market", []) if _phone(cp)]
    if not market:
        _log("no facility phone numbers configured (config phone / "
             "AUTOPILOT_PHONE_OVERRIDE) — nothing to dial")
        return
    try:
        phones = [_phone(cp) for cp in market]
        parallel = len(set(phones)) == len(phones)  # duplicate targets → sequential

        def _one(cp):
            _log(f"round 1 — calling {cp['facility_name']}…")
            out = calls.start_call(_phone(cp), cp["facility_name"],
                                   negotiate=False, spec_id=spec_id)
            _log(f"{cp['facility_name']}: {_wait_done(out['conversation_id'])}")

        if parallel:
            _log(f"dialing all {len(market)} facilities in parallel")
            threads = [threading.Thread(target=_one, args=(cp,), daemon=True)
                       for cp in market]
            for t in threads:
                t.start()
                time.sleep(1.5)  # stagger initiation slightly
            for t in threads:
                t.join(timeout=480)
        else:
            _log("shared phone target detected — calling sequentially")
            for cp in market:
                _one(cp)
                time.sleep(3)

        ranked = [q for q in rank_quotes(spec_id)["ranked"] if q["total"]]
        if len(ranked) < 2:
            _log("fewer than 2 usable quotes — skipping negotiation round")
        else:
            best = ranked[0]
            target = max(ranked, key=lambda q: q["effective_total"])
            cp = next((c for c in market
                       if c["facility_name"] == target["facility_name"]), None)
            if cp is None or target["facility_name"] == best["facility_name"]:
                _log("no distinct negotiation target — skipping round 2")
            else:
                _log(f"round 2 — negotiating with {target['facility_name']} "
                     f"(real leverage: ${best['total']:.0f} from {best['facility_name']})")
                out = calls.start_call(_phone(cp), cp["facility_name"],
                                       negotiate=True, spec_id=spec_id)
                _log(f"negotiation: {_wait_done(out['conversation_id'])}")
        _log("autopilot finished — ledger is live, generate the report anytime")
    except Exception as e:
        _log(f"error: {e}")
    finally:
        STATE["running"] = False


def kick_off(spec_id: str) -> bool:
    """Start the market round in the background; returns False if already busy."""
    if STATE["running"]:
        _log("kick_off ignored — a run is already in progress")
        return False
    STATE["running"] = True
    STATE["log"].clear()
    _log(f"autopilot engaged for spec {spec_id}")
    threading.Thread(target=_run, args=(spec_id,), daemon=True).start()
    return True
