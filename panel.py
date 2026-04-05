#!/usr/bin/env python3
"""
panel.py — CLI entry point for Panel v1.

Usage:
  panel "my idea text" --domain auto
  panel "my idea text" --domain strategy
  panel --file idea.md --domain coding
  panel --calibration  (show calibration summary)

Runs: classify → cast → run (parallel) → synthesize → save report → feedback
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from classifier import classify, classify_primary
from caster import cast, format_cast
from runner import run_panel_sync
from synthesis import synthesize
from feedback import interactive_feedback, get_calibration_summary

OUTPUT_DIR = Path(__file__).parent / "output"


def save_report(report: str, domain: str) -> Path:
    """Save report to output directory, return path."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-{domain}.md"
    path = OUTPUT_DIR / filename
    path.write_text(report)
    return path


def run(
    text: str,
    domain: str = "auto",
    panel_size: int = 7,
    context: str = None,
    skip_feedback: bool = False,
    quiet: bool = False,
) -> dict:
    """
    Full panel pipeline.

    Returns dict with grade, report, and output path.
    """
    start = time.time()

    # ── Step 1: Classify ──
    if domain == "auto":
        if not quiet:
            print("Classifying domain...")
        scores = classify(text)
        domain = scores[0][0]
        if not quiet:
            for d, s in scores:
                bar = "█" * int(s * 20)
                print(f"  {d:12s} {s:.3f} {bar}")
            print(f"  → Using: {domain}\n")
    else:
        if not quiet:
            print(f"Domain: {domain}\n")

    # ── Step 2: Cast ──
    if not quiet:
        print("Casting panel...")
    assignments = cast(domain, panel_size)
    if not quiet:
        print(format_cast(assignments))
        print()

    # ── Step 3: Run ──
    if not quiet:
        print(f"Running {len(assignments)} panelists in parallel...")
    # Prepend context if provided
    full_input = text
    if context:
        full_input = f"CONTEXT: {context}\n\nIDEA/INPUT:\n{text}"

    results = run_panel_sync(assignments, full_input)

    errors = [r for r in results if r.get("error")]
    valid = [r for r in results if not r.get("error")]
    if not quiet:
        print(f"  ✓ {len(valid)} responded, {len(errors)} errors")
        elapsed = results[0].get("elapsed_total", 0) if results else 0
        print(f"  ⏱ {elapsed}s total\n")

    # ── Step 4: Synthesize ──
    synthesis = synthesize(results, text, domain)
    if not quiet:
        print(f"Grade: {synthesis['grade']} ({synthesis['consensus_score']}/10)")
        print(f"Build votes: {synthesis['build_votes']}")
        print(f"Variance: {synthesis['variance']}")
        if synthesis["flags"]:
            print("Flags:")
            for f in synthesis["flags"]:
                print(f"  ⚠ {f}")
        print()

    # ── Step 5: Save ──
    output_path = save_report(synthesis["report"], domain)
    if not quiet:
        print(f"Report saved: {output_path}\n")

    # ── Step 6: Feedback ──
    if not skip_feedback and not quiet:
        interactive_feedback(results, domain)

    total_time = round(time.time() - start, 1)
    if not quiet:
        print(f"\nTotal time: {total_time}s")

    return {
        "grade": synthesis["grade"],
        "consensus_score": synthesis["consensus_score"],
        "report": synthesis["report"],
        "output_path": str(output_path),
        "domain": domain,
        "elapsed": total_time,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Panel v1 — Multi-model idea evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  panel "Should I build an AI sales assistant?"
  panel "Should I build an AI sales assistant?" --domain strategy
  panel --file ~/ideas/panel-concept.md --domain auto
  panel --calibration
        """,
    )
    parser.add_argument("text", nargs="?", help="Idea or text to evaluate")
    parser.add_argument("--domain", default="auto",
                        choices=["auto", "strategy", "coding", "writing", "creative"],
                        help="Domain (default: auto-detect)")
    parser.add_argument("--file", "-f", help="Read input from file")
    parser.add_argument("--size", "-s", type=int, default=7,
                        choices=[5, 7, 9],
                        help="Panel size: 5 (compact), 7 (default), 9 (swarm)")
    parser.add_argument("--context", "-c",
                        help="Context prefix (e.g. 'internal tool, not a product')")
    parser.add_argument("--no-feedback", action="store_true",
                        help="Skip interactive feedback")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Minimal output (just the report)")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")
    parser.add_argument("--calibration", action="store_true",
                        help="Show calibration summary and exit")

    args = parser.parse_args()

    if args.calibration:
        print(get_calibration_summary())
        return

    # Get input text
    text = args.text
    if args.file:
        text = Path(args.file).read_text()
    if not text:
        # Read from stdin if piped
        if not sys.stdin.isatty():
            text = sys.stdin.read().strip()

    if not text:
        parser.print_help()
        sys.exit(1)

    # Check API key
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not set")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)

    result = run(text, args.domain, args.size, args.context, args.no_feedback, args.quiet)

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.quiet:
        print(result["report"])


if __name__ == "__main__":
    main()
