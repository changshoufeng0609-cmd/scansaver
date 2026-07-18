"""Create (or recreate) all ElevenLabs agents from the prompt templates +
vertical config. Run after every prompt/config change:

    python -m scripts.setup_agents

Writes the resulting ids to agents/agent_ids.json (read by backend + start_call).

Config-not-code in action: the <<PLACEHOLDER>> tokens below are filled from the
vertical config, so swapping VERTICAL_CONFIG retargets every agent's prompt.
{{double_brace}} tokens are left intact — they are ElevenLabs runtime dynamic
variables.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.elevenlabs_client import create_agent, webhook_tool  # noqa: E402
from backend.spec_utils import line_item_checklist, load_config, render_lever_lines  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"

# VERIFY: exact LLM id strings in ElevenLabs docs (/docs/agents-platform/customization/llm).
DEFAULT_LLM = os.environ.get("ELEVENLABS_LLM", "claude-sonnet-4")

# Premade ElevenLabs voices — swap freely; VERIFY ids in your dashboard's Voices tab.
VOICES = {
    "estimator": "21m00Tcm4TlvDq8ikWAM",   # Rachel
    "caller": "pNInz6obpgDQGcFmaJgB",      # Adam
    "stonewaller": "MF3mGyEYCl7XYWbV9V6O", # Elli
    "lowballer": "TxGEqnHWrfWFTfGW9XjX",   # Josh
    "upseller": "EXAVITQu4vr4xnSDxMaL",    # Sarah/Bella
}


def render(template_path: Path, replacements: dict) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"<<{key}>>", value)
    leftovers = [line for line in text.splitlines() if "<<" in line]
    if leftovers:
        raise ValueError(f"Unfilled placeholders in {template_path.name}: {leftovers}")
    return text


def main():
    config = load_config()
    base_url = os.environ.get("PUBLIC_BASE_URL")
    if not base_url:
        raise SystemExit("Set PUBLIC_BASE_URL in .env (your ngrok https URL) first.")
    base_url = base_url.rstrip("/")

    intake_q = "\n".join(
        f"- ({q['id']}) {q['ask']}"
        + ("  [\"I don't know\" is acceptable]" if q.get("unknown_ok") else "")
        for q in config["intake_questions"]
    )
    honesty = "\n".join(f"- {r}" for r in config["honesty_rules"])

    common = {
        "DISPLAY_NAME": config["display_name"],
        "INTAKE_QUESTIONS": intake_q,
        "HONESTY_RULES": honesty,
        "LINE_ITEMS": line_item_checklist(config),
        "NEGOTIATION_LEVERS": render_lever_lines(config, has_best_quote=True),
    }

    ids = {}

    # ---- The Estimator (intake) ----
    spec_props = config["job_spec_schema"]["properties"]
    submit_spec = webhook_tool(
        name="submit_spec",
        description=("Submit the completed, verbally-confirmed job specification. "
                     "Call exactly once, only after the user confirms the summary."),
        url=f"{base_url}/tools/submit_spec",
        properties={"spec": {"type": "object", "properties": spec_props,
                             "description": "The full job spec object."}},
        required=["spec"],
    )
    ids["estimator"] = create_agent(
        name="ScanSaver — Estimator",
        system_prompt=render(AGENTS_DIR / "estimator.md", common),
        first_message=("Hi! I'll help you shop this around so you never overpay. "
                       "First, a couple of quick questions — what kind of scan do "
                       "you need?"),
        tools=[submit_spec],
        llm=DEFAULT_LLM,
        voice_id=VOICES["estimator"],
    )

    # ---- The Caller / Closer (outbound) ----
    log_quote = webhook_tool(
        name="log_quote",
        description=("Log a quote as soon as you have usable numbers. Call again "
                     "with the new total if the price changes during the call."),
        url=f"{base_url}/tools/log_quote",
        properties={
            "spec_id": {"type": "string", "description": "The Spec ID from your instructions."},
            "facility_name": {"type": "string"},
            "total": {"type": "number", "description": "All-in total as stated. 0 only if truly none given."},
            "line_items": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "One of the configured line-item ids."},
                "label": {"type": "string"},
                "amount": {"type": "number"}}}},
            "itemized": {"type": "boolean", "description": "False if they refused to break the price down."},
            "read_included": {"type": "boolean", "description": "False if the professional read is separate or unclear."},
            "notes": {"type": "string", "description": "Validity window, written-quote promise, whether the price moved during the call, etc."},
        },
        required=["facility_name", "total", "itemized", "read_included"],
    )
    log_outcome = webhook_tool(
        name="log_outcome",
        description="Mandatory before hanging up: record the structured outcome of this call.",
        url=f"{base_url}/tools/log_outcome",
        properties={
            "spec_id": {"type": "string", "description": "The Spec ID from your instructions."},
            "facility_name": {"type": "string"},
            "outcome_type": {"type": "string", "enum": config["call_outcomes"]},
            "details": {"type": "string", "description": "Callback name/time/number, or the verbatim decline reason."},
        },
        required=["facility_name", "outcome_type", "details"],
    )
    ids["caller"] = create_agent(
        name="ScanSaver — Caller/Closer",
        system_prompt=render(AGENTS_DIR / "caller.md", common),
        first_message=("Hi, I'm calling to get a price on a scan for a customer "
                       "— do you have a quick minute?"),
        tools=[log_quote, log_outcome],
        llm=DEFAULT_LLM,
        voice_id=VOICES["caller"],
    )

    # ---- Counterparty market (for agent-to-agent runs / rehearsal) ----
    for cp in config.get("counterparty_market", []):
        key = cp["agent_key"]
        path = AGENTS_DIR / "counterparties" / f"{key}.md"
        if not path.exists():
            print(f"skip counterparty {key}: no prompt file")
            continue
        ids[key] = create_agent(
            name=f"Counterparty — {cp['facility_name']} ({key})",
            system_prompt=path.read_text(encoding="utf-8"),
            first_message=f"Thanks for calling {cp['facility_name']}, how can I help you?",
            llm=DEFAULT_LLM,
            voice_id=VOICES.get(key),
        )

    out = AGENTS_DIR / "agent_ids.json"
    out.write_text(json.dumps(ids, indent=2))
    print(f"Wrote {out}:\n{json.dumps(ids, indent=2)}")
    print("\nNext steps:")
    print("  1. In the ElevenLabs dashboard, set the Estimator agent to allow the")
    print("     public web widget (or wire SDK auth) so frontend/index.html can load it.")
    print("  2. Point your workspace post-call webhook at "
          f"{base_url}/webhooks/post_call")
    print("  3. Import a Twilio number (Phone Numbers tab) and put its id in .env "
          "as ELEVENLABS_PHONE_NUMBER_ID.")


if __name__ == "__main__":
    main()
