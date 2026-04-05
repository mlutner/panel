"""
caster.py — Model selection + role assignment algorithm.

For a given domain, loads the role definitions and available models,
then selects one model per role using a scoring algorithm that considers:
  (a) Domain strength
  (b) Historical effectiveness (calibration.json)
  (c) Diversity distance from already-selected models
  (d) Stance alignment (contrarian models → adversarial roles, etc.)

Constraints:
  - Max 1 model per provider (if possible given panel size)
  - Adversarial roles get lowest agreement_rate models
  - Wild card gets highest temperature model
  - Constructive roles get models that won't hedge
"""

import json
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"


def _load_models() -> list[dict]:
    with open(CONFIG_DIR / "models.yaml") as f:
        data = yaml.safe_load(f)
    return data.get("models", [])


def _load_domain_roles(domain: str, panel_size: int = 7) -> list[dict]:
    domain_file = CONFIG_DIR / "domains" / f"{domain}.yaml"
    if not domain_file.exists():
        domain_file = CONFIG_DIR / "domains" / "strategy.yaml"
    with open(domain_file) as f:
        data = yaml.safe_load(f)

    roles = data.get("roles", [])

    # Filter by tier based on panel_size
    if panel_size <= 5:
        roles = [r for r in roles if r.get("tier") not in ("extended", "swarm")]
    elif panel_size <= 7:
        roles = [r for r in roles if r.get("tier") not in ("swarm",)]
    # else: include all (swarm mode)

    return roles[:panel_size]


def _load_calibration() -> dict:
    cal_file = CONFIG_DIR / "calibration.json"
    with open(cal_file) as f:
        return json.load(f)


def _calibration_score(cal: dict, model_id: str, domain: str, role: str) -> float:
    """Historical performance. Returns 2.5 (neutral) if no data."""
    entry = cal.get(model_id, {}).get(domain, {}).get(role, {})
    if entry and entry.get("run_count", 0) > 0:
        return entry["avg"]
    return 2.5


def _score_model_for_role(
    model: dict,
    role: dict,
    domain: str,
    calibration: dict,
    selected_providers: set,
    selected_origins: set,
) -> float:
    """Score a model for a role. Higher = better fit."""
    domain_score = model.get("domain_scores", {}).get(domain, 0.5)
    cal = _calibration_score(calibration, model["id"], domain, role["name"]) / 5.0

    # Provider diversity: strong penalty for reusing providers
    provider_penalty = -0.5 if model["provider"] in selected_providers else 0.15

    # Origin diversity: bonus for different training lineages
    origin_bonus = 0.1 if model.get("origin", "") not in selected_origins else -0.1

    # Stance alignment
    stance = role.get("stance", "neutral")
    agreement = model.get("agreement_rate", 0.5)
    stance_score = 0
    if stance == "adversarial":
        stance_score = (1.0 - agreement) * 0.3  # lower agreement = better adversary
    elif stance == "constructive":
        stance_score = agreement * 0.2  # higher agreement = better champion
    elif stance == "wild_card":
        # Prefer models with high temperature and unconventional strengths
        if "unconventional" in model.get("strengths", []) or "creative" in model.get("strengths", []):
            stance_score = 0.2

    # Strength match
    role_prefs = role.get("select_for", {}).get("prefer", [])
    model_strengths = set(model.get("strengths", []))
    overlap = len(set(role_prefs) & model_strengths)
    strength_bonus = overlap * 0.08

    score = domain_score * 0.3 + cal * 0.2 + provider_penalty + origin_bonus + stance_score + strength_bonus
    return round(score, 3)


def cast(domain: str, panel_size: int = 7) -> list[dict]:
    """
    Select one model per role for the given domain.

    Args:
        domain: strategy, coding, writing, creative
        panel_size: 5 (compact), 7 (default), 9 (swarm)

    Returns:
        list of {model, role, role_prompt, stance, temperature, score}
    """
    models = _load_models()
    roles = _load_domain_roles(domain, panel_size)
    calibration = _load_calibration()

    # Sort roles by assignment priority:
    # adversarial first (most constrained), then wild_card, then neutral, then constructive
    stance_priority = {"adversarial": 0, "wild_card": 1, "neutral": 2, "constructive": 3}
    sorted_roles = sorted(roles, key=lambda r: stance_priority.get(r.get("stance", "neutral"), 2))

    assignments = []
    selected_providers = set()
    selected_origins = set()
    selected_model_ids = set()

    for role in sorted_roles:
        available = [m for m in models if m["id"] not in selected_model_ids]

        # If we've used all unique models, allow provider reuse
        if not available:
            available = [m for m in models]

        scored = []
        for m in available:
            s = _score_model_for_role(m, role, domain, calibration, selected_providers, selected_origins)
            scored.append((m, s))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_model, best_score = scored[0]

        # Use per-role temperature if specified, else model default, else 0.7
        temp = role.get("temperature", best_model.get("temperature", 0.7))

        assignments.append({
            "model": best_model,
            "role": role["name"],
            "role_prompt": role["prompt"],
            "stance": role.get("stance", "neutral"),
            "temperature": temp,
            "score": best_score,
        })
        selected_providers.add(best_model["provider"])
        selected_origins.add(best_model.get("origin", ""))
        selected_model_ids.add(best_model["id"])

    # Re-sort by stance for readability: constructive → analytical → adversarial → wild
    display_order = {"constructive": 0, "neutral": 1, "adversarial": 2, "wild_card": 3}
    assignments.sort(key=lambda a: display_order.get(a["stance"], 2))

    return assignments


def format_cast(assignments: list[dict]) -> str:
    lines = [
        f"PANEL CAST ({len(assignments)} members)",
        "=" * 55,
    ]
    current_stance = None
    for a in assignments:
        if a["stance"] != current_stance:
            current_stance = a["stance"]
            label = {"constructive": "FOR", "neutral": "NEUTRAL", "adversarial": "AGAINST", "wild_card": "WILD CARD"}
            lines.append(f"\n  ── {label.get(current_stance, current_stance)} ──")
        m = a["model"]
        lines.append(f"  {a['role']:22s} → {m['name']} (t={a['temperature']})")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    domain = sys.argv[1] if len(sys.argv) > 1 else "strategy"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    assignments = cast(domain, size)
    print(format_cast(assignments))
