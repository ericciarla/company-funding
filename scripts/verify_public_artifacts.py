#!/usr/bin/env python3
"""Verify the public funding artifacts without network or paid API calls.

Checks invariants rather than constants. The previous version asserted the
2026-08-04 publication literally -- 300 cases, 3,900 runs, 13 leaderboard rows,
300 eligible for every provider -- so it could only ever pass against that one
frozen file. Those numbers now move every cycle: enrichment grows as freshness
snapshots age into it, each freshness snapshot is its own size, and providers
join at different times.

The properties that must hold regardless:

  * every leaderboard row reconciles against its own cells
  * a provider is scored on the cases it was actually measured on, never a
    board-wide total
  * pooled freshness equals the pooled recomputation of its snapshots
  * no literal vendor response bodies are redistributed
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/latest-funding.json"
INPUTS = ROOT / "data/funding/company-funding-inputs-v1.csv"
FIELDS = {"latest_stage", "latest_date", "latest_amount", "total_raised", "round_count"}
METRICS = {"stage_eligible", "stage_returned", "stage_correct", "llm_judge"}
EXPORT_PROVIDERS = {"crunchbase", "harmonic"}


def present(value: Any) -> bool:
    """Zero is a returned value. See the matching note in the exporter."""
    return value not in (None, "")


def check_runs(label: str, cases: list[dict], runs: list[dict]) -> None:
    slugs = {case["case_slug"] for case in cases}
    assert len(slugs) == len(cases), f"{label}: duplicate case_slug"
    assert len({case["input_domain"] for case in cases}) == len(cases), f"{label}: duplicate input_domain"
    assert all(run["case_slug"] in slugs for run in runs), f"{label}: run references an unknown case"
    assert len({(r["case_slug"], r["provider_slug"], r.get("snapshot")) for r in runs}) == len(runs), \
        f"{label}: duplicate (case, provider) cell"
    # Redistribution guard: normalized contract only, never a literal body.
    assert all("raw" not in run for run in runs), f"{label}: a run carries a raw response body"
    assert all(set(run.get("normalized") or {}) == FIELDS for run in runs), f"{label}: normalized keys drift"
    assert all(set(run["metrics"]) == METRICS for run in runs), f"{label}: metric names drift"
    assert all((run["metrics"]["llm_judge"] or {}).get("reason") for run in runs), f"{label}: a judge verdict has no reason"
    assert all((run["metrics"]["llm_judge"] or {}).get("decision_basis") for run in runs), f"{label}: a judge verdict has no decision_basis"


def check_leaderboard(label: str, runs: list[dict], rows: list[dict]) -> None:
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        by_provider[run["provider_slug"]].append(run)
    assert {row["provider_slug"] for row in rows} == set(by_provider), f"{label}: leaderboard roster differs from the cells"

    for row in rows:
        provider = by_provider[row["provider_slug"]]
        slug = row["provider_slug"]
        case_count = len({run["case_slug"] for run in provider})
        # The substantive check: each provider's denominator is its own case
        # count. Enrichment holds cases only the late joiners were run against,
        # so a board-wide denominator would understate everyone else.
        assert row["case_count"] == case_count, f"{label}/{slug}: case_count {row['case_count']} != {case_count} measured"
        assert row["eligible_stage_cases"] == sum(r["metrics"]["stage_eligible"] for r in provider), f"{label}/{slug}: eligible mismatch"
        assert row["correct_stage_count"] == sum(r["metrics"]["stage_correct"] for r in provider), f"{label}/{slug}: correct mismatch"
        assert row["cases_attempted"] == len(provider), f"{label}/{slug}: attempted mismatch"
        assert row["cases_resolved"] == sum(r["status"] == "ok" for r in provider), f"{label}/{slug}: resolved mismatch"
        fields = sum(sum(present(r["normalized"].get(f)) for f in FIELDS) for r in provider)
        expected = round(100 * fields / (len(provider) * len(FIELDS)), 2)
        assert row["funding_field_coverage_pct"] == expected, \
            f"{label}/{slug}: coverage {row['funding_field_coverage_pct']} != recomputed {expected}"
        if row["eligible_stage_cases"]:
            assert row["stage_correct_yield_pct"] == round(100 * row["correct_stage_count"] / row["eligible_stage_cases"], 2), \
                f"{label}/{slug}: yield does not follow from correct/eligible"

    ranks = sorted(row["rank"] for row in rows)
    assert ranks == list(range(1, len(rows) + 1)), f"{label}: ranks are not 1..n"

    # Export-sourced providers must never carry inferred latency or cost.
    for slug in EXPORT_PROVIDERS & set(by_provider):
        assert all(r["latency_ms"] is None for r in by_provider[slug]), f"{label}/{slug}: export has a latency value"
        assert all(r["cost_units"] is None for r in by_provider[slug]), f"{label}/{slug}: export has a cost value"


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert snapshot["status"] == "complete"
    assert snapshot["schema_version"] == "3.0", f"unexpected schema_version {snapshot['schema_version']}"
    boards = snapshot["boards"]

    enrichment = boards["enrichment"]
    e_cases, e_runs, e_rows = enrichment["cases"], enrichment["runs"], enrichment["leaderboard"]
    check_runs("enrichment", e_cases, e_runs)
    check_leaderboard("enrichment", e_runs, e_rows)
    assert enrichment["case_count"] == len(e_cases)

    # The frozen input list must still describe the enrichment cohort it seeded.
    with INPUTS.open(encoding="utf-8", newline="") as handle:
        inputs = list(csv.DictReader(handle))
    input_domains = {row["company_domain"] for row in inputs}
    case_domains = {case["input_domain"] for case in e_cases}
    assert input_domains <= case_domains, \
        f"{len(input_domains - case_domains)} frozen input domains are absent from the enrichment board"

    freshness = boards["freshness"]
    pooled_runs: list[dict] = []
    for entry in freshness["snapshots"]:
        path = ROOT / entry["path"]
        assert path.exists(), f"missing freshness snapshot file: {entry['path']}"
        snap = json.loads(path.read_text(encoding="utf-8"))
        assert snap["dataset_slug"] == entry["slug"], f"{entry['path']}: slug does not match the manifest"
        assert snap["case_count"] == entry["case_count"] == len(snap["cases"]), f"{entry['path']}: case_count mismatch"
        assert {r["provider_slug"] for r in snap["runs"]} == {r["provider_slug"] for r in snap["leaderboard"]}
        assert entry["provider_count"] == len(snap["leaderboard"]), f"{entry['path']}: provider_count mismatch"
        check_runs(entry["label"], snap["cases"], snap["runs"])
        check_leaderboard(entry["label"], snap["runs"], snap["leaderboard"])
        pooled_runs.extend(snap["runs"])

    # Pooled freshness has to be exactly the pooled recomputation of the files
    # it indexes, or the combined artifact and its parts disagree.
    check_leaderboard("freshness/pooled", pooled_runs, freshness["leaderboard"])
    for row in freshness["leaderboard"]:
        snaps = {r["snapshot"] for r in pooled_runs if r["provider_slug"] == row["provider_slug"]}
        assert row["snapshot_count"] == len(snaps), \
            f"freshness/{row['provider_slug']}: snapshot_count {row['snapshot_count']} != {len(snaps)}"

    print(f"enrichment: {len(e_cases)} companies, {len(e_runs)} cells, {len(e_rows)} providers")
    print(f"  denominators: {sorted({row['case_count'] for row in e_rows})}")
    for entry in freshness["snapshots"]:
        print(f"freshness {entry['label']}: {entry['case_count']} companies, {entry['provider_count']} providers, window {entry['window'][0]}..{entry['window'][1]}")
    print(f"freshness pooled: {len(pooled_runs)} cells, {len(freshness['leaderboard'])} providers")
    print("artifact verification passed; network calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
