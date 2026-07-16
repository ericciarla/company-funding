#!/usr/bin/env python3
"""Recompute the public leaderboard from normalized snapshot data; no API calls."""
from __future__ import annotations

import json
from pathlib import Path

from build_public_snapshot import OUTPUT, leaderboard
from funding.score_funding_stage_dry_run import canonical_stage


def main() -> int:
    snapshot = json.loads(OUTPUT.read_text(encoding="utf-8"))
    truth = {case["case_slug"]: canonical_stage(case["reference"]["latest_stage"]) for case in snapshot["cases"]}
    for run in snapshot["runs"]:
        expected = truth[run["case_slug"]]
        actual = canonical_stage((run.get("normalized") or {}).get("latest_stage"))
        run["metrics"] = {
            "stage_eligible": int(expected is not None), "stage_returned": int(expected is not None and actual is not None),
            "stage_correct": int(expected is not None and actual == expected),
            "truth_stage_canonical": expected, "provider_stage_canonical": actual,
        }
    snapshot["leaderboard"] = leaderboard(snapshot["cases"], snapshot["runs"])
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recomputed {len(snapshot['runs'])} runs; network calls: 0")


if __name__ == "__main__":
    raise SystemExit(main())
