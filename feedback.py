"""
feedback.py — Post-run rating + calibration update.

After reading the panel report, the user rates which panelist was most useful.
This updates calibration.json so the casting algorithm improves over time.
"""

import json
from pathlib import Path

CALIBRATION_FILE = Path(__file__).parent / "config" / "calibration.json"


def _load_calibration() -> dict:
    """Load calibration data."""
    with open(CALIBRATION_FILE) as f:
        return json.load(f)


def _save_calibration(data: dict):
    """Save calibration data."""
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_feedback(
    results: list[dict],
    domain: str,
    ratings: dict[str, int],
):
    """
    Record user feedback for panel run.

    Args:
        results: panelist results from runner
        domain: the domain this run was for
        ratings: dict of role_name → score (1-5)
                 e.g. {"CFO": 4, "Devils Advocate": 5, "Operator": 2}
    """
    calibration = _load_calibration()

    for result in results:
        if result.get("error"):
            continue

        role = result["role"]
        model_id = result["model"]
        rating = ratings.get(role)
        if rating is None:
            continue

        # Initialize nested structure if needed
        if model_id not in calibration:
            calibration[model_id] = {}
        if domain not in calibration[model_id]:
            calibration[model_id][domain] = {}
        if role not in calibration[model_id][domain]:
            calibration[model_id][domain][role] = {
                "total_score": 0,
                "run_count": 0,
                "avg": 0,
            }

        entry = calibration[model_id][domain][role]
        entry["total_score"] += rating
        entry["run_count"] += 1
        entry["avg"] = round(entry["total_score"] / entry["run_count"], 2)

    _save_calibration(calibration)


def interactive_feedback(results: list[dict], domain: str):
    """
    Interactive CLI feedback loop. Asks user to rate each panelist.

    Returns the ratings dict.
    """
    print("\n" + "=" * 50)
    print("FEEDBACK — Rate each panelist (1-5, or Enter to skip)")
    print("=" * 50)

    valid = [r for r in results if r.get("error") is None]
    ratings = {}

    for r in valid:
        role = r["role"]
        model_name = r.get("model_name", r["model"])
        while True:
            raw = input(f"  {role} ({model_name}): ").strip()
            if not raw:
                break  # skip
            try:
                score = int(raw)
                if 1 <= score <= 5:
                    ratings[role] = score
                    break
                else:
                    print("    (1-5 please)")
            except ValueError:
                print("    (number 1-5 or Enter to skip)")

    if ratings:
        record_feedback(results, domain, ratings)
        print(f"\n  ✓ Calibration updated ({len(ratings)} ratings recorded)")
    else:
        print("\n  Skipped — no calibration update")

    return ratings


def get_calibration_summary() -> str:
    """Return a human-readable calibration summary."""
    cal = _load_calibration()
    lines = ["CALIBRATION SUMMARY", "=" * 50]

    for model_id, domains in cal.items():
        if model_id == "_meta":
            continue
        lines.append(f"\n{model_id}:")
        for domain, roles in domains.items():
            for role, data in roles.items():
                lines.append(
                    f"  {domain}/{role}: {data['avg']:.1f} avg "
                    f"({data['run_count']} runs)"
                )

    if len(lines) == 2:
        lines.append("  (no data yet — run some panels and rate them)")

    return "\n".join(lines)
