"""Thin ElevenLabs Agents REST client.

Verified against live docs 2026-07-18 (https://elevenlabs.io/docs/llms.txt,
now under the /docs/eleven-agents/ namespace):
  - Tools are workspace resources: create via POST /v1/convai/tools with
    {"tool_config": {...}}, then reference by id in the agent's
    conversation_config.agent.prompt.tool_ids. Inline prompt.tools is gone.
  - Agent create: POST /v1/convai/agents/create, voice via
    conversation_config.tts.voice_id.
  - Outbound: POST /v1/convai/twilio/outbound-call
    {agent_id, agent_phone_number_id, to_number,
     conversation_initiation_client_data.dynamic_variables};
    response {success, message, conversation_id, callSid}.
  - Audio: GET /v1/convai/conversations/{id}/audio.
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
    """Webhook tool_config, per /docs/api-reference/tools/create."""
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


def create_tool(tool_config: dict) -> str:
    """Create a workspace tool resource, return its id (referenced via
    prompt.tool_ids — inline agent tools no longer exist in the API)."""
    r = httpx.post(f"{BASE}/v1/convai/tools", headers=_headers(),
                   json={"tool_config": tool_config}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def delete_tool(tool_id: str) -> None:
    httpx.delete(f"{BASE}/v1/convai/tools/{tool_id}", headers=_headers(),
                 timeout=30).raise_for_status()


def delete_agent(agent_id: str) -> None:
    httpx.delete(f"{BASE}/v1/convai/agents/{agent_id}", headers=_headers(),
                 timeout=30).raise_for_status()


def list_voice_ids() -> set[str]:
    """Ids of voices visible to this workspace (premade + cloned)."""
    r = httpx.get(f"{BASE}/v1/voices", headers=_headers(), timeout=30)
    r.raise_for_status()
    return {v["voice_id"] for v in r.json().get("voices", [])}


def create_agent(name: str, system_prompt: str, first_message: str,
                 tool_ids: list[str] | None = None, llm: str | None = None,
                 voice_id: str | None = None, language: str = "en") -> str:
    """Create an agent, return agent_id."""
    prompt_block = {"prompt": system_prompt}
    if llm:
        prompt_block["llm"] = llm
    if tool_ids:
        prompt_block["tool_ids"] = tool_ids
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
    """Start one outbound call via the native Twilio integration."""
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
    """Fetch call recording for playback in the report UI."""
    r = httpx.get(f"{BASE}/v1/convai/conversations/{conversation_id}/audio",
                  headers=_headers(), timeout=60)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest
