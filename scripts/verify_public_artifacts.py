#!/usr/bin/env python3
"""Verify the frozen public funding artifacts without network or paid API calls."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/latest-funding.json"
INPUTS = ROOT / "data/funding/company-funding-inputs-v1.csv"
PROVIDERS = {"apollo", "company-enrich", "explorium", "fiber", "ocean", "people-data-labs", "predictleads"}
EXPECTED_CORRECT = {"fiber": 207, "apollo": 150, "people-data-labs": 132, "predictleads": 116, "company-enrich": 96, "explorium": 40, "ocean": 11}
EXPECTED_RECENCY = {"3_24_months": 134, "31_90_days": 79, "8_30_days": 50, "0_7_days": 37}


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    with INPUTS.open(encoding="utf-8", newline="") as handle: inputs = list(csv.DictReader(handle))
    cases, runs, rows = snapshot["cases"], snapshot["runs"], snapshot["leaderboard"]
    assert snapshot["status"] == "complete"
    assert len(inputs) == len(cases) == snapshot["case_count"] == 300
    assert len({case["input_domain"] for case in cases}) == 300
    assert Counter(case["recency_bucket"] for case in cases) == EXPECTED_RECENCY
    assert len(runs) == 2100
    assert {run["provider_slug"] for run in runs} == PROVIDERS
    assert len({(run["case_slug"], run["provider_slug"]) for run in runs}) == 2100
    assert all("raw" not in run for run in runs)
    assert all(set((run.get("normalized") or {})) == {"latest_stage", "latest_date", "latest_amount", "total_raised", "round_count"} for run in runs)
    assert len(rows) == 7
    assert {row["provider_slug"] for row in rows} == PROVIDERS
    assert all(row["eligible_stage_cases"] == 268 for row in rows)
    actual = {row["provider_slug"]: row["correct_stage_count"] for row in rows}
    assert actual == EXPECTED_CORRECT
    print("final companies: 300")
    print("provider cells: 2100")
    print("scored stage labels: 268")
    print(f"recency buckets: {dict(sorted(Counter(case['recency_bucket'] for case in cases).items()))}")
    print("artifact verification passed; network calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
