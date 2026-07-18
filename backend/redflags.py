"""Red-flag engine. All rules come from the vertical config; this module only
interprets them. Rule types:

- type "price":    {"metric": "total", "op": "lt"|"gt", "factor": F, "of": "<benchmark key>"}
                   fires when total <op> F * benchmark[of]
- type "structure": fired from quote payload booleans (itemized / read_included)
- type "outcome":  fired from the call outcome type (e.g. documented_decline)
"""


def _flag(rule: dict) -> dict:
    return {
        "id": rule["id"],
        "severity": rule.get("severity", "medium"),
        "label": rule.get("label", rule["id"]),
        "explanation": rule.get("explanation", ""),
    }


def evaluate_quote(total: float, itemized: bool, read_included: bool,
                   benchmark: dict | None, config: dict) -> list[dict]:
    flags = []
    for rule in config.get("red_flags", []):
        rtype = rule.get("type")
        if rtype == "price" and benchmark and total is not None:
            r = rule.get("rule", {})
            ref = benchmark.get(r.get("of", ""), None)
            if ref is None:
                continue
            threshold = r.get("factor", 1.0) * ref
            if r.get("op") == "lt" and total < threshold:
                flags.append(_flag(rule))
            elif r.get("op") == "gt" and total > threshold:
                flags.append(_flag(rule))
        elif rtype == "structure":
            if rule["id"] == "no_itemization" and not itemized:
                flags.append(_flag(rule))
            elif rule["id"] == "unbundled_read" and not read_included:
                flags.append(_flag(rule))
    return flags


def evaluate_outcome(outcome_type: str, config: dict) -> list[dict]:
    flags = []
    for rule in config.get("red_flags", []):
        if rule.get("type") != "outcome":
            continue
        if rule["id"] == "refused_to_quote" and outcome_type == "documented_decline":
            flags.append(_flag(rule))
    return flags
