"""Vertical-config helpers: load config, resolve benchmarks, render the
dynamic-variable strings that get injected into every call.

Design rule (from the challenge brief): everything vertical-specific comes from
the config file. This module reads config; it never hardcodes imaging logic.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    path = os.environ.get("VERTICAL_CONFIG", "config/medical_imaging.json")
    with open(ROOT / path, encoding="utf-8") as f:
        return json.load(f)


def resolve_cpt(spec: dict, config: dict) -> str | None:
    """Best-effort CPT lookup from cpt_map keys like 'MRI|ankle|without'."""
    if spec.get("cpt_code"):
        return spec["cpt_code"]
    scan = (spec.get("scan_type") or "").strip()
    part = (spec.get("body_part") or "").lower()
    contrast = spec.get("contrast") or "without"
    for key, entry in config.get("cpt_map", {}).items():
        k_scan, k_part, k_contrast = key.split("|")
        if k_scan == scan and k_part in part and k_contrast == contrast:
            return entry["cpt"]
    return None


def get_benchmark(spec: dict, config: dict) -> dict | None:
    cpt = resolve_cpt(spec, config)
    by_cpt = config.get("benchmarks", {}).get("by_cpt", {})
    if cpt and cpt in by_cpt:
        return {"cpt": cpt, **by_cpt[cpt]}
    return None


def spec_to_job_summary(spec: dict, config: dict) -> str:
    """One consistent paragraph describing the job — reused verbatim on every
    call, which is what makes the quotes comparable."""
    parts = []
    schema_props = config["job_spec_schema"]["properties"]
    skip = {"notes", "insurance", "cpt_code"}
    for field in schema_props:
        if field in skip:
            continue
        val = spec.get(field)
        if val in (None, "", [], "unknown"):
            continue
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        label = field.replace("_", " ")
        parts.append(f"{label}: {val}")
    cpt = resolve_cpt(spec, config)
    if cpt:
        parts.append(f"CPT code: {cpt}")
    if spec.get("notes"):
        parts.append(f"notes: {spec['notes']}")
    return "; ".join(parts) + "."


def payment_line(spec: dict) -> str:
    if spec.get("payment_mode") == "cash":
        return "Cash / self-pay. The customer wants the best all-in cash price."
    ins = spec.get("insurance") or {}
    return (
        f"Insurance: {ins.get('carrier', 'unknown carrier')} "
        f"{ins.get('plan', '')}".strip()
        + ". Ask for both the insurance estimate and the cash price."
    )


def line_item_checklist(config: dict) -> str:
    return "\n".join(f"- {li['label']}" for li in config["quote_line_items"])


def render_lever_lines(config: dict, has_best_quote: bool) -> str:
    lines = []
    for lever in config.get("negotiation_levers", []):
        if lever.get("requires_best_quote") and not has_best_quote:
            continue
        lines.append(f"- {lever['line']}")
    return "\n".join(lines)


def benchmark_line(spec: dict, config: dict) -> str:
    b = get_benchmark(spec, config)
    if not b:
        return "No market benchmark available for this job."
    cur = config.get("currency", "USD")
    return (
        f"Market benchmark for {b['label']}: typical cash range "
        f"{b['cash_low']}–{b['cash_high']} {cur}, median ~{b['cash_median']}, "
        f"Medicare floor ~{b['medicare_floor']}."
    )
