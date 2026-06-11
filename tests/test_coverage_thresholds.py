from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_coverage_thresholds.py"


def _run_check(tmp_path: Path, totals: dict[str, float]) -> subprocess.CompletedProcess[str]:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(json.dumps({"totals": totals}), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json-file",
            str(coverage_json),
            "--min-total",
            "80",
            "--min-statement",
            "88.5",
            "--min-branch",
            "75.0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_coverage_threshold_script_passes_when_all_thresholds_are_met(tmp_path: Path) -> None:
    result = _run_check(
        tmp_path,
        {
            "percent_covered": 86.28,
            "percent_statements_covered": 88.98,
            "percent_branches_covered": 75.21,
        },
    )

    assert result.returncode == 0
    assert "Coverage threshold check" in result.stdout
    assert "branch: 75.21% (min 75.00%)" in result.stdout


def test_coverage_threshold_script_fails_when_branch_floor_regresses(tmp_path: Path) -> None:
    result = _run_check(
        tmp_path,
        {
            "percent_covered": 86.28,
            "percent_statements_covered": 88.98,
            "percent_branches_covered": 74.99,
        },
    )

    assert result.returncode == 1
    assert "Coverage threshold failure:" in result.stderr
    assert "branch 74.99% < 75.00%" in result.stderr


def test_coverage_threshold_script_fails_when_statement_floor_regresses(tmp_path: Path) -> None:
    result = _run_check(
        tmp_path,
        {
            "percent_covered": 86.28,
            "percent_statements_covered": 88.49,
            "percent_branches_covered": 75.21,
        },
    )

    assert result.returncode == 1
    assert "statement 88.49% < 88.50%" in result.stderr
