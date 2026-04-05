"""
synthesis.py — Dissent map + consensus report.

Takes the raw panelist responses and produces:
  - Dissent map: where panelists agree vs disagree
  - Consensus score: average + variance
  - Flags: unanimous weakness, fragile idea, weak dissent
  - Final markdown report with grade
"""

import statistics
from datetime import datetime


def _grade(score: float) -> str:
    """Convert average score to letter grade."""
    if score >= 8.5:
        return "A"
    elif score >= 7.5:
        return "B+"
    elif score >= 6.5:
        return "B"
    elif score >= 5.5:
        return "C+"
    elif score >= 4.5:
        return "C"
    elif score >= 3.5:
        return "D"
    else:
        return "F"


def _grade_color(grade: str) -> str:
    """Emoji indicator for grade."""
    if grade.startswith("A"):
        return "🟢"
    elif grade.startswith("B"):
        return "🔵"
    elif grade.startswith("C"):
        return "🟡"
    else:
        return "🔴"


def synthesize(results: list[dict], user_input: str, domain: str) -> dict:
    """
    Produce dissent map and consensus report from panelist results.

    Returns dict with:
      - grade: letter grade
      - consensus_score: average score
      - variance: score variance
      - flags: list of warning strings
      - dissent_map: agreement/disagreement analysis
      - report: full markdown report string
    """
    # Extract valid responses (skip errors)
    valid = [r for r in results if r.get("error") is None and r["response"].get("score", 0) > 0]
    if not valid:
        return {
            "grade": "F",
            "consensus_score": 0,
            "variance": 0,
            "flags": ["All panelists failed to respond"],
            "dissent_map": {},
            "report": "# Panel Failed\n\nNo valid responses received.",
        }

    scores = [r["response"]["score"] for r in valid]
    avg_score = statistics.mean(scores)
    score_variance = statistics.variance(scores) if len(scores) > 1 else 0
    build_votes = sum(1 for r in valid if r["response"].get("would_you_build_this"))
    confidences = [r["response"].get("confidence", 0.5) for r in valid]
    avg_confidence = statistics.mean(confidences)

    grade = _grade(avg_score)

    # ── Flags ──
    flags = []

    # Unanimous weakness: if multiple panelists flag similar weaknesses
    weaknesses = [r["response"]["weakest_point"].lower() for r in valid]
    # Simple check: if any 2+ weaknesses share 3+ words
    for i, w1 in enumerate(weaknesses):
        w1_words = set(w1.split())
        for w2 in weaknesses[i + 1:]:
            w2_words = set(w2.split())
            overlap = w1_words & w2_words - {"the", "a", "is", "to", "and", "of", "in", "for", "this", "that", "it"}
            if len(overlap) >= 3:
                flags.append(f"FIXABLE FLAW: Multiple panelists flagged similar weakness ({', '.join(list(overlap)[:5])})")
                break

    # All different weaknesses = fragile idea
    if len(set(weaknesses)) == len(weaknesses) and len(valid) >= 4:
        flags.append("FRAGILE: Every panelist found a different weakness — attack surface is wide")

    # Weak dissent: devil's advocate agrees with majority
    da_result = next((r for r in valid if r["role"] == "Devils Advocate"), None)
    if da_result and da_result["response"].get("would_you_build_this") and build_votes >= len(valid) - 1:
        flags.append("WEAK DISSENT: Devil's advocate agrees with majority — consider rerunning")

    # High variance = polarizing
    if score_variance > 4:
        flags.append(f"POLARIZING: Score variance is {score_variance:.1f} — panelists strongly disagree")

    # Low confidence
    if avg_confidence < 0.4:
        flags.append(f"LOW CONFIDENCE: Average panelist confidence is {avg_confidence:.0%}")

    # ── Dissent Map ──
    dissent_map = {
        "agreement": [],
        "disagreement": [],
    }

    # Find score clusters
    high_scorers = [r for r in valid if r["response"]["score"] >= 7]
    low_scorers = [r for r in valid if r["response"]["score"] <= 4]

    if len(high_scorers) >= 3:
        dissent_map["agreement"].append(
            f"Strong consensus ({len(high_scorers)}/{len(valid)} score 7+): idea has merit"
        )
    if len(low_scorers) >= 3:
        dissent_map["agreement"].append(
            f"Strong consensus ({len(low_scorers)}/{len(valid)} score 4-): idea has serious issues"
        )

    if high_scorers and low_scorers:
        high_roles = [r["role"] for r in high_scorers]
        low_roles = [r["role"] for r in low_scorers]
        dissent_map["disagreement"].append(
            f"{', '.join(high_roles)} vs {', '.join(low_roles)} — fundamental split"
        )

    # ── Report ──
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    input_preview = user_input[:200] + "..." if len(user_input) > 200 else user_input

    report_lines = [
        f"# Panel Report",
        f"**Date:** {timestamp}",
        f"**Domain:** {domain}",
        f"**Input:** {input_preview}",
        "",
        "---",
        "",
        f"## Grade: {_grade_color(grade)} {grade} ({avg_score:.1f}/10)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Average Score | {avg_score:.1f}/10 |",
        f"| Variance | {score_variance:.1f} |",
        f"| Build Votes | {build_votes}/{len(valid)} |",
        f"| Avg Confidence | {avg_confidence:.0%} |",
        "",
    ]

    # Flags
    if flags:
        report_lines.append("## Flags")
        for f in flags:
            report_lines.append(f"- ⚠ {f}")
        report_lines.append("")

    # Dissent map
    if dissent_map["agreement"] or dissent_map["disagreement"]:
        report_lines.append("## Dissent Map")
        if dissent_map["agreement"]:
            report_lines.append("**Agreement:**")
            for a in dissent_map["agreement"]:
                report_lines.append(f"- ✓ {a}")
        if dissent_map["disagreement"]:
            report_lines.append("**Disagreement:**")
            for d in dissent_map["disagreement"]:
                report_lines.append(f"- ✗ {d}")
        report_lines.append("")

    # Individual panelist responses
    report_lines.append("## Panelist Responses")
    report_lines.append("")

    for r in sorted(valid, key=lambda x: x["response"]["score"], reverse=True):
        resp = r["response"]
        build_emoji = "👍" if resp.get("would_you_build_this") else "👎"
        report_lines.extend([
            f"### {r['role']} ({r.get('model_name', r['model'])}) — {resp['score']}/10 {build_emoji}",
            f"- **Strongest:** {resp['strongest_point']}",
            f"- **Weakest:** {resp['weakest_point']}",
            f"- **Unanswered:** {resp['unanswered_question']}",
            f"- **Confidence:** {resp.get('confidence', 'N/A')}",
            "",
        ])

    # Errors
    errors = [r for r in results if r.get("error")]
    if errors:
        report_lines.append("## Errors")
        for e in errors:
            report_lines.append(f"- {e['role']} ({e['model']}): {e['error']}")
        report_lines.append("")

    report = "\n".join(report_lines)

    return {
        "grade": grade,
        "consensus_score": round(avg_score, 1),
        "variance": round(score_variance, 1),
        "flags": flags,
        "dissent_map": dissent_map,
        "build_votes": f"{build_votes}/{len(valid)}",
        "report": report,
    }
