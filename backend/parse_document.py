"""Document intake path: doctor's order, old bill, or referral photo/PDF ->
the SAME structured job spec schema as the voice interview (a hard requirement
in the challenge brief). Uses the Anthropic API with vision.
"""
import base64
import json
import os

import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

MEDIA_TYPES = {
    ".pdf": ("document", "application/pdf"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
}


def parse_document(file_bytes: bytes, filename: str, config: dict) -> dict:
    """Return a (possibly partial) spec dict matching config['job_spec_schema'].
    Missing fields stay absent — the Estimator interview or the UI fills gaps."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in MEDIA_TYPES:
        raise ValueError(f"Unsupported file type: {ext}")
    block_type, media_type = MEDIA_TYPES[ext]

    schema = json.dumps(config["job_spec_schema"], indent=2)
    system = (
        "You extract structured job specifications from uploaded documents "
        f"for the vertical: {config['display_name']}.\n"
        "Return ONLY a JSON object conforming to this schema — no prose, no "
        "markdown fences. Omit any field the document does not support; NEVER "
        "guess or invent values.\n\nSchema:\n" + schema
    )

    payload = {
        "model": MODEL,
        "max_tokens": 1000,
        "system": system,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": block_type,
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(file_bytes).decode(),
                    },
                },
                {"type": "text",
                 "text": "Extract the job spec from this document as JSON."},
            ],
        }],
    }
    r = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"]
                   if b.get("type") == "text")
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
