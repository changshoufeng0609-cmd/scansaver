"""Document intake path: doctor's order, old bill, or referral photo/PDF ->
the SAME structured job spec schema as the voice interview (a hard requirement
in the challenge brief). Uses the OpenAI API with vision (images) / file input
(PDF) via Chat Completions.
"""
import base64
import json
import os

import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

MEDIA_TYPES = {
    ".pdf": ("file", "application/pdf"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
}


def parse_document(file_bytes: bytes, filename: str, config: dict) -> dict:
    """Return a (possibly partial) spec dict matching config['job_spec_schema'].
    Missing fields stay absent — the Estimator interview or the UI fills gaps."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

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

    data_url = f"data:{media_type};base64," + base64.b64encode(file_bytes).decode()
    if block_type == "file":
        doc_block = {"type": "file",
                     "file": {"filename": filename, "file_data": data_url}}
    else:
        doc_block = {"type": "image_url", "image_url": {"url": data_url}}

    payload = {
        "model": MODEL,
        "max_completion_tokens": 1000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                doc_block,
                {"type": "text",
                 "text": "Extract the job spec from this document as JSON."},
            ]},
        ],
    }
    r = httpx.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
