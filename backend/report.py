"""The Closer's output: rank all quotes, attach red flags and transcript
evidence, and produce a plain-language recommendation (via Anthropic API, with a
deterministic fallback so the demo never blanks).

Ranking policy (simple, defensible, explainable):
  1. Refusals are unranked; they appear as documented declines.
  2. High-severity red flags push a quote below any clean quote.
  3. Otherwise sort by effective total, where a quote with an excluded
     radiologist read gets the benchmark-typical read cost added as a
     "realistic total" estimate so teaser prices can't win.
"""
import json
import os

import httpx

from . import db
from .spec_utils import get_benchmark, load_config, spec_to_job_summary

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
ASSUMED_READ_FEE = 200  # used only when a quote excludes the read; explained in report


def _latest_quote_per_facility(quotes: list[dict]) -> list[dict]:
    """A facility may log multiple quotes (e.g. price moved mid-negotiation).
    Keep the latest as current, but preserve history for the 'price moved' proof."""
    by_fac: dict[str, list] = {}
    for q in quotes:
        by_fac.setdefault(q["facility_name"], []).append(q)
    out = []
    for fac, qs in by_fac.items():
        current = qs[-1]
        current = dict(current)
        current["history"] = [
            {"total": q["total"], "created_at": q["created_at"]} for q in qs
        ]
        current["price_moved"] = len({q["total"] for q in qs}) > 1
        out.append(current)
    return out


def rank_quotes(spec_id: str) -> dict:
    config = load_config()
    spec_row = db.get_spec(spec_id)
    if not spec_row:
        raise ValueError(f"spec {spec_id} not found")
    quotes = _latest_quote_per_facility(db.list_quotes(spec_id))
    outcomes = db.list_outcomes(spec_id)
    benchmark = get_benchmark(spec_row["spec"], config)

    for q in quotes:
        effective = q["total"] or 0
        if not q["read_included"]:
            effective += ASSUMED_READ_FEE
            q["effective_note"] = (
                f"Radiologist read excluded — realistic total assumes "
                f"+${ASSUMED_READ_FEE} for the read."
            )
        q["effective_total"] = effective
        q["high_flags"] = sum(1 for f in q["red_flags"] if f["severity"] == "high")
        q["med_flags"] = sum(1 for f in q["red_flags"] if f["severity"] == "medium")

    # Trust beats teaser: clean quotes outrank flagged ones before price decides.
    ranked = sorted(quotes, key=lambda q: (q["high_flags"], q["med_flags"],
                                           q["effective_total"]))
    declines = [o for o in outcomes if o["outcome_type"] == "documented_decline"]
    callbacks = [o for o in outcomes if o["outcome_type"] == "callback_commitment"]

    return {
        "spec": spec_row["spec"],
        "benchmark": benchmark,
        "ranked": ranked,
        "declines": declines,
        "callbacks": callbacks,
    }


def _transcript_snippets(spec_id: str, max_chars: int = 4000) -> str:
    """Concatenate stored transcripts (from post-call webhooks) as citable evidence."""
    chunks = []
    for call in db.list_calls(spec_id):
        if not call.get("transcript_json"):
            continue
        turns = json.loads(call["transcript_json"])
        lines = [f"[{call['facility_name']} — conversation {call['conversation_id']}]"]
        for t in turns:
            role = t.get("role", "?")
            msg = t.get("message") or t.get("text") or ""
            if msg:
                lines.append(f"{role}: {msg}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)[:max_chars]


def generate_report(spec_id: str) -> dict:
    config = load_config()
    data = rank_quotes(spec_id)
    evidence = _transcript_snippets(spec_id)

    recommendation = _fallback_text(data)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            recommendation = _claude_recommendation(data, evidence, config, api_key)
        except Exception as e:  # never let the report page blank in a demo
            recommendation += f"\n\n(LLM explanation unavailable: {e})"

    data["recommendation"] = recommendation
    data["evidence_excerpt"] = evidence
    return data


def _fallback_text(data: dict) -> str:
    if not data["ranked"]:
        return "No quotes collected yet."
    best = data["ranked"][0]
    return (
        f"Best available option: {best['facility_name']} at "
        f"${best['effective_total']:.0f} effective total "
        f"({len(best['red_flags'])} red flag(s))."
    )


def _claude_recommendation(data: dict, evidence: str, config: dict,
                           api_key: str) -> str:
    summary = spec_to_job_summary(data["spec"], config)
    payload = {
        "model": MODEL,
        "max_tokens": 700,
        "system": (
            "You write the final consumer-facing recommendation for a "
            "price-shopping voice agent. Plain language, no hype. Explain which "
            "offer to take and why, why the runners-up lost (cite red flags), "
            "and quote 1-2 short verbatim lines from the transcripts as "
            "evidence, attributed to the facility. If any price moved during a "
            "call, call that out explicitly. Under 250 words."
        ),
        "messages": [{
            "role": "user",
            "content": (
                f"Job: {summary}\n\n"
                f"Benchmark: {json.dumps(data['benchmark'])}\n\n"
                f"Ranked quotes: {json.dumps(data['ranked'], default=str)}\n\n"
                f"Declines: {json.dumps(data['declines'], default=str)}\n\n"
                f"Callbacks: {json.dumps(data['callbacks'], default=str)}\n\n"
                f"Transcript evidence:\n{evidence}"
            ),
        }],
    }
    r = httpx.post(
        ANTHROPIC_URL,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=payload, timeout=60,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"]
                   if b.get("type") == "text")
