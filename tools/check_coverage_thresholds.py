#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate explicit repository coverage thresholds from a coverage "
            "JSON report."
        )
    )
    parser.add_argument("--json-file", required=True, help="Path to coverage JSON output.")
    parser.add_argument("--min-total", type=float, required=True, help="Minimum combined total.")
    parser.add_argument(
        "--min-statement",
        type=float,
        required=True,
        help="Minimum statement coverage percentage.",
    )
    parser.add_argument(
        "--min-branch",
        type=float,
        required=True,
        help="Minimum branch coverage percentage.",
    )
    return parser.parse_args()


def load_metrics(json_file: Path) -> dict[str, float]:
    data = json.loads(json_file.read_text(encoding="utf-8"))
    totals = data.get("totals", {})
    return {
        "combined total": float(totals.get("percent_covered", 0.0)),
        "statement": float(totals.get("percent_statements_covered", 0.0)),
        "branch": float(totals.get("percent_branches_covered", 0.0)),
    }


def main() -> int:
    args = parse_args()
    json_file = Path(args.json_file)
    if not json_file.exists():
        print(f"Coverage JSON not found: {json_file}", file=sys.stderr)
        return 1

    try:
        metrics = load_metrics(json_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Failed to read coverage JSON {json_file}: {exc}", file=sys.stderr)
        return 1

    thresholds = {
        "combined total": args.min_total,
        "statement": args.min_statement,
        "branch": args.min_branch,
    }
    failures: list[str] = []

    print("Coverage threshold check")
    for label in ("combined total", "statement", "branch"):
        actual = metrics[label]
        minimum = thresholds[label]
        print(f"- {label}: {actual:.2f}% (min {minimum:.2f}%)")
        if actual < minimum:
            failures.append(f"{label} {actual:.2f}% < {minimum:.2f}%")

    if failures:
        print("Coverage threshold failure:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
