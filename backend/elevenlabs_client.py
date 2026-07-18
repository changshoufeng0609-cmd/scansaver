"""Thin ElevenLabs Agents REST client.

!! VERIFY-WITH-DOCS !!
The ElevenLabs Agents API evolves quickly. Every payload shape below was correct
at scaffold time but MUST be verified against the live docs before first run.
Every docs page is fetchable as plain markdown: append `.md` to any docs URL, or
append `/llms.txt` for a page index (start at https://elevenlabs.io/docs/llms.txt).
Key pages:
  - Agent create/update:  /docs/api-reference/agents/create
  - Server tools:         /docs/agents-platform/customization/tools  (tools may
                          now be workspace resources referenced by id — adapt
                          `webhook_tool` + create_agent if so)
  - Outbound via Twilio:  /docs/api-reference/twilio/outbound-call
  - Batch calling:        /docs/agents-platform/phone-numbers/batch-calls
  - Post-call webhooks:   /docs/agents-platform/workflows/post-call-webhooks
See CLAUDE.md -> "Verify with live docs" for the checklist.
"""
import os
from pathlib import Path

import httpx

BASE = "https://api.elevenlabs.io"


def _headers():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    return {"xi-api-key": key}


def webhook_tool(name: str, description: str, url: str, properties: dict,
                 required: list[str]) -> dict:
    """Server-tool (webhook) definition attached to an agent.
    VERIFY: current tool schema in docs; adjust here only — callers are agnostic."""
    return {
        "type": "webhook",
        "name": name,
        "description": description,
        "api_schema": {
            "url": url,
            "method": "POST",
            "request_body_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def create_agent(name: str, system_prompt: str, first_message: str,
                 tools: list[dict] | None = None, llm: str | None = None,
                 voice_id: str | None = None, language: str = "en") -> str:
    """Create an agent, return agent_id.
    VERIFY: conversation_config shape + LLM id strings (docs: /docs/agents-platform/customization/llm).
    """
    prompt_block = {"prompt": system_prompt}
    if llm:
        prompt_block["llm"] = llm
    if tools:
        prompt_block["tools"] = tools
    payload = {
        "name": name,
        "conversation_config": {
            "agent": {
                "first_message": first_message,
                "language": language,
                "prompt": prompt_block,
            },
        },
    }
    if voice_id:
        payload["conversation_config"]["tts"] = {"voice_id": voice_id}
    r = httpx.post(f"{BASE}/v1/convai/agents/create", headers=_headers(),
                   json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["agent_id"]


def outbound_call(agent_id: str, agent_phone_number_id: str, to_number: str,
                  dynamic_variables: dict) -> dict:
    """Start one outbound call via the native Twilio integration.
    VERIFY: field names in /docs/api-reference/twilio/outbound-call ."""
    payload = {
        "agent_id": agent_id,
        "agent_phone_number_id": agent_phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": {
            "dynamic_variables": dynamic_variables,
        },
    }
    r = httpx.post(f"{BASE}/v1/convai/twilio/outbound-call", headers=_headers(),
                   json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def get_conversation(conversation_id: str) -> dict:
    r = httpx.get(f"{BASE}/v1/convai/conversations/{conversation_id}",
                  headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def download_audio(conversation_id: str, dest: Path) -> Path:
    """Fetch call recording for playback in the report UI.
    VERIFY: endpoint path in docs (conversations -> get audio)."""
    r = httpx.get(f"{BASE}/v1/convai/conversations/{conversation_id}/audio",
                  headers=_headers(), timeout=60)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest
