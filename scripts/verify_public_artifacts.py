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
PROVIDERS = {"apollo", "company-enrich", "crunchbase", "crustdata", "exa", "explorium", "fiber", "ocean", "parallel", "people-data-labs", "predictleads"}
EXPECTED_RECENCY = {"3_24_months": 134, "31_90_days": 79, "8_30_days": 50, "0_7_days": 37}


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    with INPUTS.open(encoding="utf-8", newline="") as handle: inputs = list(csv.DictReader(handle))
    cases, runs, rows = snapshot["cases"], snapshot["runs"], snapshot["leaderboard"]
    assert snapshot["status"] == "complete"
    assert snapshot["schema_version"] == "2.0"
    assert snapshot["dataset_slug"] == "company-funding-enrichment-v2-llm-judge"
    assert len(inputs) == len(cases) == snapshot["case_count"] == 300
    assert len({case["input_domain"] for case in cases}) == 300
    assert Counter(case["recency_bucket"] for case in cases) == EXPECTED_RECENCY
    assert len(runs) == 3300
    assert {run["provider_slug"] for run in runs} == PROVIDERS
    assert len({(run["case_slug"], run["provider_slug"]) for run in runs}) == 3300
    assert all("raw" not in run for run in runs)
    assert all(set((run.get("normalized") or {})) == {"latest_stage", "latest_date", "latest_amount", "total_raised", "round_count"} for run in runs)
    assert len(rows) == 11
    assert {row["provider_slug"] for row in rows} == PROVIDERS
    assert all(row["eligible_stage_cases"] == 300 for row in rows)
    assert all(set(run["metrics"]) == {"stage_eligible", "stage_returned", "stage_correct", "llm_judge"} for run in runs)
    assert all((run["metrics"]["llm_judge"] or {}).get("reason") for run in runs)
    assert all((run["metrics"]["llm_judge"] or {}).get("decision_basis") for run in runs)
    for row in rows:
        provider = [run for run in runs if run["provider_slug"] == row["provider_slug"]]
        assert sum(run["metrics"]["stage_eligible"] for run in provider) == row["eligible_stage_cases"]
        assert sum(run["metrics"]["stage_correct"] for run in provider) == row["correct_stage_count"]
    crunchbase_runs = [run for run in runs if run["provider_slug"] == "crunchbase"]
    assert len(crunchbase_runs) == 300
    assert all(run["latency_ms"] is None for run in crunchbase_runs)
    assert all((run.get("audit") or {}).get("source") == "csv_export" for run in crunchbase_runs)
    print("final companies: 300")
    print("provider cells: 3300")
    print("Ground Truth-reviewed companies: 300")
    print(f"recency buckets: {dict(sorted(Counter(case['recency_bucket'] for case in cases).items()))}")
    print("artifact verification passed; network calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
