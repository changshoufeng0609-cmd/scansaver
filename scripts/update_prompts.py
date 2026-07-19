"""Re-render agent prompts from agents/*.md + config and PATCH them onto the
EXISTING agents (ids unchanged) — unlike setup_agents, this preserves the
widget-public setting, phone-number assignment, and conversation history.

    python -m scripts.update_prompts            # all agents
    python -m scripts.update_prompts estimator  # just one

Use setup_agents only when tools/agents must be created from scratch.
"""
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.elevenlabs_client import BASE, _headers  # noqa: E402
from backend.spec_utils import line_item_checklist, load_config, render_lever_lines  # noqa: E402
from scripts.setup_agents import AGENTS_DIR, render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def build_prompts(config) -> dict:
    intake_q = "\n".join(
        f"- ({q['id']}) {q['ask']}"
        + ("  [\"I don't know\" is acceptable]" if q.get("unknown_ok") else "")
        for q in config["intake_questions"]
    )
    common = {
        "DISPLAY_NAME": config["display_name"],
        "INTAKE_QUESTIONS": intake_q,
        "HONESTY_RULES": "\n".join(f"- {r}" for r in config["honesty_rules"]),
        "LINE_ITEMS": line_item_checklist(config),
        "NEGOTIATION_LEVERS": render_lever_lines(config, has_best_quote=True),
    }
    prompts = {
        "estimator": render(AGENTS_DIR / "estimator.md", common),
        "caller": render(AGENTS_DIR / "caller.md", common),
    }
    for cp in config.get("counterparty_market", []):
        path = AGENTS_DIR / "counterparties" / f"{cp['agent_key']}.md"
        if path.exists():
            prompts[cp["agent_key"]] = path.read_text(encoding="utf-8")
    return prompts


def main():
    config = load_config()
    ids = json.loads((ROOT / "agents" / "agent_ids.json").read_text())
    prompts = build_prompts(config)
    only = sys.argv[1] if len(sys.argv) > 1 else None

    for key, prompt in prompts.items():
        if only and key != only:
            continue
        if key not in ids:
            print(f"skip {key}: no agent id")
            continue
        aid = ids[key]
        cfg = httpx.get(f"{BASE}/v1/convai/agents/{aid}", headers=_headers(),
                        timeout=30).json()["conversation_config"]
        cfg["agent"]["prompt"]["prompt"] = prompt
        cfg["agent"]["prompt"].pop("tools", None)  # API rejects tools+tool_ids
        r = httpx.patch(f"{BASE}/v1/convai/agents/{aid}", headers=_headers(),
                        json={"conversation_config": cfg}, timeout=30)
        r.raise_for_status()
        print(f"updated {key} ({len(prompt)} chars)")


if __name__ == "__main__":
    main()
