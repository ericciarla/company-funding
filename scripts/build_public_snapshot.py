#!/usr/bin/env python3
"""Build the public normalized snapshot from local runner checkpoints.

Literal vendor HTTP bodies are intentionally omitted from the publication file.
Pass ``--raw-dir`` only when rebuilding from a separate local checkpoint store.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from funding.score_funding_stage_dry_run import canonical_stage

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/funding/company-funding-inputs-v1.csv"
DEFAULT_RAW_V1 = ROOT / "data/funding/provider-runs-v1/raw"
DEFAULT_RAW_V2 = ROOT / "data/funding/provider-runs-v2/raw"
OUTPUT = ROOT / "data/latest-funding.json"
PROVIDERS = {
    "fiber": "Fiber", "predictleads": "PredictLeads", "apollo": "Apollo",
    "people-data-labs": "People Data Labs", "ocean": "Ocean.io",
    "explorium": "Explorium", "company-enrich": "CompanyEnrich",
    "crunchbase": "Crunchbase", "exa": "Exa", "parallel": "Parallel",
    "crustdata": "Crustdata", "zoominfo": "ZoomInfo",
}
PROVIDER_RAW_DIR = {
    **{slug: "v1" for slug in (
        "fiber", "predictleads", "apollo", "people-data-labs", "ocean",
        "explorium", "company-enrich",
    )},
    **{slug: "v2" for slug in ("crunchbase", "exa", "parallel", "crustdata", "zoominfo")},
}
FIELDS = ("latest_stage", "latest_date", "latest_amount", "total_raised", "round_count")


def present(value: Any) -> bool:
    return value not in (None, "")


def case_from_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "case_slug": row["candidate_id"], "input_name": row["company_name"],
        "input_domain": row["company_domain"], "recency_bucket": row["recency_bucket"],
        "stage_bucket": row["stage_bucket"],
        "reference": {
            "latest_stage": row["ground_truth_stage"] or None,
            "latest_announced_on": row["ground_truth_announced_on"] or None,
            "latest_amount": row["ground_truth_amount"] or None,
            "currency": row["ground_truth_currency"] or None,
            "total_raised": row["ground_truth_total_raised"] or None,
            "official_source_url": row["official_source_url"],
            "official_source_kind": row["official_source_kind"],
            "official_source_publisher": row["official_source_publisher"],
            "official_published_at": row["official_published_at"] or None,
            "evidence_confidence": row["evidence_confidence"],
            "evidence_quote": row["evidence_quote"],
            "review_status": row["review_status"],
        },
    }


def normalized_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Project v1/v2 normalized records onto the stable public schema."""
    normalized = raw.get("normalized") or {}
    def first_present(*values: Any) -> Any:
        return next((value for value in values if value not in (None, "")), None)

    return {
        "latest_stage": normalized.get("latest_stage"),
        "latest_date": first_present(normalized.get("latest_date"), normalized.get("latest_announced_on")),
        "latest_amount": normalized.get("latest_amount"),
        "total_raised": normalized.get("total_raised"),
        "round_count": first_present(normalized.get("round_count"), normalized.get("funding_round_count")),
    }


def build_runs(cases: list[dict[str, Any]], raw_v1: Path, raw_v2: Path) -> list[dict[str, Any]]:
    by_domain = {case["input_domain"]: case for case in cases}
    runs: list[dict[str, Any]] = []
    for slug, name in PROVIDERS.items():
        raw_dir = raw_v1 if PROVIDER_RAW_DIR[slug] == "v1" else raw_v2
        files = sorted((raw_dir / slug).glob("*.json"))
        if len(files) != len(cases):
            raise RuntimeError(f"{slug}: expected {len(cases)} checkpoint files, found {len(files)}")
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8"))
            domain = raw["input"]["domain"]
            case = by_domain.get(domain)
            if not case:
                raise RuntimeError(f"{slug}: unknown checkpoint domain {domain!r}")
            normalized = normalized_fields(raw)
            truth = canonical_stage(case["reference"]["latest_stage"])
            prediction = canonical_stage(normalized.get("latest_stage"))
            eligible = truth is not None
            runs.append({
                "case_slug": case["case_slug"], "provider_slug": slug, "provider_name": name,
                "status": raw.get("status") or "error", "latency_ms": raw.get("latency_ms"),
                "error": raw.get("failure_reason"), "queried_at": raw.get("completed_at"),
                "normalized": normalized,
                "audit": {"source": raw.get("source"), "funding_related_paths": raw.get("funding_related_paths") or [], "prior_attempt_count": len(raw.get("prior_attempts") or [])},
                "metrics": {
                    "stage_eligible": int(eligible),
                    "stage_returned": int(eligible and prediction is not None),
                    "stage_correct": int(eligible and prediction == truth),
                    "truth_stage_canonical": truth,
                    "provider_stage_canonical": prediction,
                },
            })
    return runs


def leaderboard(cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for slug, name in PROVIDERS.items():
        provider = [run for run in runs if run["provider_slug"] == slug]
        eligible = sum(run["metrics"]["stage_eligible"] for run in provider)
        returned = sum(run["metrics"]["stage_returned"] for run in provider)
        correct = sum(run["metrics"]["stage_correct"] for run in provider)
        fields_returned = sum(sum(present(run["normalized"].get(field)) for field in FIELDS) for run in provider)
        latencies = sorted(run["latency_ms"] for run in provider if isinstance(run["latency_ms"], (int, float)))
        rows.append({
            "provider_slug": slug, "provider_name": name, "total_cases": len(cases),
            "cases_attempted": len(provider), "cases_resolved": sum(run["status"] == "ok" for run in provider),
            "resolution_rate_pct": round(100 * sum(run["status"] == "ok" for run in provider) / len(cases), 2),
            "eligible_stage_cases": eligible, "correct_stage_count": correct,
            "stage_correct_yield_pct": round(100 * correct / eligible, 2),
            "stage_fill_rate_pct": round(100 * returned / eligible, 2),
            "stage_accuracy_when_present_pct": round(100 * correct / returned, 2) if returned else None,
            "funding_field_coverage_pct": round(100 * fields_returned / (len(provider) * len(FIELDS)), 2),
            "avg_funding_fields_returned": round(fields_returned / len(provider), 2),
            "median_latency_ms": round(latencies[len(latencies) // 2], 1) if latencies else None,
            "p90_latency_ms": round(latencies[round((len(latencies) - 1) * .9)], 1) if latencies else None,
        })
    rows.sort(key=lambda row: (-row["stage_correct_yield_pct"], -row["resolution_rate_pct"], row["provider_slug"]))
    for rank, row in enumerate(rows, 1): row["rank"] = rank
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-v1-dir", type=Path, default=DEFAULT_RAW_V1)
    parser.add_argument("--raw-v2-dir", type=Path, default=DEFAULT_RAW_V2)
    args = parser.parse_args()
    with INPUT.open(encoding="utf-8", newline="") as handle:
        cases = [case_from_row(row) for row in csv.DictReader(handle)]
    if not cases or len({case["input_domain"] for case in cases}) != len(cases):
        raise RuntimeError(f"{INPUT} is empty or has duplicate domains")
    runs = build_runs(cases, args.raw_v1_dir, args.raw_v2_dir)
    snapshot = {
        "schema_version": "1.0", "dataset_slug": "company-funding-enrichment-v1",
        "dataset_name": "Company Funding Enrichment — 300-Company Cohort", "status": "complete",
        "reference_status": "research_confirmed_v1", "case_count": len(cases),
        "providers": PROVIDERS, "evaluated_fields": list(FIELDS),
        "stage_metric": "correct canonical latest stage / cases with specific canonical reference stage",
        "case_counts_by_recency_bucket": dict(sorted(Counter(case["recency_bucket"] for case in cases).items())),
        "cases": cases, "runs": runs, "leaderboard": leaderboard(cases, runs),
    }
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(cases)} cases, {len(runs)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
