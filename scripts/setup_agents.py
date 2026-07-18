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

from backend.elevenlabs_client import (create_agent, create_tool, delete_agent,  # noqa: E402
                                       delete_tool, list_voice_ids, webhook_tool)
from backend.spec_utils import line_item_checklist, load_config, render_lever_lines  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"

# Verified against the live LLM enum 2026-07-18. Other valid Anthropic ids:
# claude-sonnet-4-6, claude-sonnet-4, claude-haiku-4-5, claude-opus-4-7.
DEFAULT_LLM = os.environ.get("ELEVENLABS_LLM", "claude-sonnet-4-5")

# Premade ElevenLabs voices — swap freely; ids are checked against the
# workspace's voice list at setup time and fall back to default if missing.
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


def cleanup_previous_run(ids_path: Path):
    """Agents + tools are workspace resources; delete last run's before
    recreating so reruns don't litter the workspace."""
    if not ids_path.exists():
        return
    old = json.loads(ids_path.read_text())
    for key, agent_id in old.items():
        if key == "_tools":
            continue
        try:
            delete_agent(agent_id)
        except Exception as e:
            print(f"  (could not delete old agent {key}: {e})")
    for name, tool_id in old.get("_tools", {}).items():
        try:
            delete_tool(tool_id)
        except Exception as e:
            print(f"  (could not delete old tool {name}: {e})")


def checked_voice(voice_ids: set[str] | None, key: str) -> str | None:
    vid = VOICES.get(key)
    if vid and voice_ids is not None and vid not in voice_ids:
        print(f"  WARNING: voice {vid} ({key}) not in workspace — using agent default voice.")
        return None
    return vid


def main():
    config = load_config()
    base_url = os.environ.get("PUBLIC_BASE_URL")
    if not base_url:
        raise SystemExit("Set PUBLIC_BASE_URL in .env (your ngrok https URL) first.")
    base_url = base_url.rstrip("/")

    try:
        voice_ids = list_voice_ids()
    except Exception as e:
        print(f"  (could not list voices, skipping voice check: {e})")
        voice_ids = None

    ids_path = AGENTS_DIR / "agent_ids.json"
    cleanup_previous_run(ids_path)

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
    tool_ids = {}

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
    tool_ids["submit_spec"] = create_tool(submit_spec)
    ids["estimator"] = create_agent(
        name="ScanSaver — Estimator",
        system_prompt=render(AGENTS_DIR / "estimator.md", common),
        first_message=("Hi! I'll help you shop this around so you never overpay. "
                       "First, a couple of quick questions — what kind of scan do "
                       "you need?"),
        tool_ids=[tool_ids["submit_spec"]],
        llm=DEFAULT_LLM,
        voice_id=checked_voice(voice_ids, "estimator"),
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
    tool_ids["log_quote"] = create_tool(log_quote)
    tool_ids["log_outcome"] = create_tool(log_outcome)
    ids["caller"] = create_agent(
        name="ScanSaver — Caller/Closer",
        system_prompt=render(AGENTS_DIR / "caller.md", common),
        first_message=("Hi, I'm calling to get a price on a scan for a customer "
                       "— do you have a quick minute?"),
        tool_ids=[tool_ids["log_quote"], tool_ids["log_outcome"]],
        llm=DEFAULT_LLM,
        voice_id=checked_voice(voice_ids, "caller"),
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
            voice_id=checked_voice(voice_ids, key),
        )

    ids["_tools"] = tool_ids
    ids_path.write_text(json.dumps(ids, indent=2))
    print(f"Wrote {ids_path}:\n{json.dumps(ids, indent=2)}")
    print("\nNext steps (dashboard, one-time):")
    print("  1. Estimator agent → Advanced tab → disable authentication ('public"
          " agent') so the web widget in frontend/index.html can load it. "
          "Optionally add your domain in Security → Allowlist.")
    print("  2. ElevenAgents settings → post-call webhooks → point at "
          f"{base_url}/webhooks/post_call (enable 'transcription'; 'audio' too "
          "if you want recordings pushed instead of pulled).")
    print("  3. Phone Numbers tab → import your Twilio number, copy its id into "
          ".env as ELEVENLABS_PHONE_NUMBER_ID.")


if __name__ == "__main__":
    main()
