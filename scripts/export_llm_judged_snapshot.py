#!/usr/bin/env python3
"""Export the public funding snapshot without literal vendor response bodies.

The benchmark is two boards:

  enrichment  rounds announced more than 30 days ago, one growing dataset
  freshness   rounds in the trailing 30 days, one dated snapshot per cycle

Both are written to data/latest-funding.json under ``boards``. Each freshness
snapshot's cells additionally go to data/freshness/<YYYY-MM>.json, indexed from
the combined file, so the combined file stays bounded as snapshots accumulate
while every snapshot remains individually reproducible.

Requires SNAPSHOT_SUPABASE_URL and SNAPSHOT_SUPABASE_SERVICE_ROLE_KEY. Point
them at whichever database holds the published data.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/latest-funding.json"
FRESHNESS_DIR = ROOT / "data/freshness"
SCHEMA_VERSION = "3.0"
FAMILY = {"enrichment": "funding-enrichment", "freshness": "funding-freshness"}
FIELDS = ("latest_stage", "latest_date", "latest_amount", "total_raised", "round_count")
METRIC_NAMES = {"resolved", "stage_eligible", "stage_returned", "stage_correct", "stage_llm_judge"}
REFERENCE_KEYS = ("official_source_url", "official_source_kind", "official_source_publisher",
                  "official_published_at", "evidence_confidence", "evidence_quote", "review_status")


def fetch(client: Any, table: str, dataset_id: str, fields: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, 100_000, 1_000):
        page = client.table(table).select(fields).eq("dataset_id", dataset_id).range(offset, offset + 999).execute().data
        rows.extend(page)
        if len(page) < 1_000:
            return rows
    raise RuntimeError(f"pagination overflow for {table}")


def present(value: Any) -> bool:
    """Zero is a returned value, not a missing one.

    This used to be `a or b` coalescing, which silently discarded
    `round_count: 0` and understated coverage for every provider that reports a
    genuine zero. It cost Apollo, CompanyEnrich and Fiber several points in the
    2026-08-04 publication.
    """
    return value not in (None, "")


def first_present(*values: Any) -> Any:
    return next((value for value in values if present(value)), None)


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """One five-field contract for every provider, whichever schema it emitted."""
    return {
        "latest_stage": raw.get("latest_stage"),
        "latest_date": first_present(raw.get("latest_date"), raw.get("latest_announced_on")),
        "latest_amount": raw.get("latest_amount"),
        "total_raised": raw.get("total_raised"),
        "round_count": first_present(raw.get("round_count"), raw.get("funding_round_count")),
    }


def leaderboard(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-provider denominators, mirroring leaderboardFromCells(pooled) on the site.

    A provider is scored against the cases it was actually measured on, never a
    board-wide total. That matters in two places: enrichment holds cases only
    the late-joining providers were run against, and pooled freshness spans
    snapshots that providers joined at different times.
    """
    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_provider[run["provider_slug"]].append(run)

    rows = []
    for slug, provider in sorted(by_provider.items()):
        case_count = len({run["case_slug"] for run in provider})
        snapshot_count = len({run.get("snapshot") for run in provider if run.get("snapshot")}) or 1
        eligible = sum(run["metrics"]["stage_eligible"] for run in provider)
        returned = sum(run["metrics"]["stage_returned"] for run in provider)
        correct = sum(run["metrics"]["stage_correct"] for run in provider)
        # Correct AND returned. A case can be scored correct while returning no
        # stage at all: the judge policy passes any vendor answer when Ground
        # Truth is blank, and accepts a blank answer when it is Undisclosed.
        # Dividing raw correct by returned therefore exceeded 100%.
        correct_and_returned = sum(
            min(run["metrics"]["stage_correct"], run["metrics"]["stage_returned"])
            for run in provider
        )
        fields = sum(sum(present(run["normalized"].get(f)) for f in FIELDS) for run in provider)
        resolved = sum(run["status"] == "ok" for run in provider)
        attempted = len(provider)
        rows.append({
            "provider_slug": slug,
            "provider_name": provider[0]["provider_name"],
            "total_cases": case_count,
            "case_count": case_count,
            "snapshot_count": snapshot_count,
            "cases_attempted": attempted,
            "cases_resolved": resolved,
            "resolution_rate_pct": round(100 * resolved / case_count, 2) if case_count else None,
            "eligible_stage_cases": eligible,
            "correct_stage_count": correct,
            "stage_correct_yield_pct": round(100 * correct / eligible, 2) if eligible else None,
            "stage_fill_rate_pct": round(100 * returned / eligible, 2) if eligible else None,
            "stage_accuracy_when_present_pct": round(100 * correct_and_returned / returned, 2) if returned else None,
            "funding_field_coverage_pct": round(100 * fields / (attempted * len(FIELDS)), 2) if attempted else None,
            "avg_funding_fields_returned": round(fields / attempted, 2) if attempted else None,
        })
    rows.sort(key=lambda r: (-(r["stage_correct_yield_pct"] or -1), -(r["resolution_rate_pct"] or -1), r["provider_slug"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def load_dataset(client: Any, dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_cases = fetch(client, "funding_cases", dataset["id"], "*")
    source_runs = fetch(
        client, "funding_runs", dataset["id"],
        "id,case_id,status,normalized_response,audit_response,latency_ms,cost_units,cost_unit,error,queried_at,providers(slug,name)",
    )
    if not source_cases:
        raise RuntimeError(f"{dataset['slug']} has no cases")

    metrics_by_run: dict[str, dict[str, Any]] = defaultdict(dict)
    ids = [run["id"] for run in source_runs]
    for start in range(0, len(ids), 100):
        for metric in client.table("funding_run_metrics").select("run_id,metric_name,metric_value,detail").in_("run_id", ids[start:start + 100]).execute().data:
            metrics_by_run[metric["run_id"]][metric["metric_name"]] = metric

    case_by_id = {case["id"]: case for case in source_cases}
    cases = []
    for case in source_cases:
        attributes = case.get("reference_attributes") or {}
        metadata = case.get("source_metadata") or {}
        cases.append({
            "case_slug": case["case_slug"], "input_name": case.get("input_name"),
            "input_domain": case["input_domain"], "recency_bucket": case.get("recency_bucket"),
            "stage_bucket": case.get("stage_bucket"),
            "latest_announced_on": case.get("latest_announced_on"),
            "reference": {**attributes, **{k: metadata.get(k) for k in REFERENCE_KEYS}},
        })

    runs = []
    for source in source_runs:
        metrics = metrics_by_run[source["id"]]
        if set(metrics) != METRIC_NAMES:
            raise RuntimeError(f"incomplete metrics for run {source['id']} in {dataset['slug']}")
        audit = source.get("audit_response") or {}
        runs.append({
            "case_slug": case_by_id[source["case_id"]]["case_slug"],
            "provider_slug": source["providers"]["slug"], "provider_name": source["providers"]["name"],
            "snapshot": dataset["slug"],
            "status": source["status"], "latency_ms": source.get("latency_ms"),
            "cost_units": source.get("cost_units"), "cost_unit": source.get("cost_unit"),
            "error": source.get("error"), "queried_at": source.get("queried_at"),
            "normalized": normalize(source.get("normalized_response") or {}),
            "audit": {k: audit.get(k) for k in ("source", "funding_related_paths", "prior_attempt_count", "failure_reason", "sources", "reasoning_effort")},
            "metrics": {
                "stage_eligible": metrics["stage_eligible"]["metric_value"],
                "stage_returned": metrics["stage_returned"]["metric_value"],
                "stage_correct": metrics["stage_correct"]["metric_value"],
                "llm_judge": metrics["stage_llm_judge"].get("detail") or {},
            },
        })
    cases.sort(key=lambda c: c["case_slug"])
    runs.sort(key=lambda r: (r["case_slug"], r["provider_slug"]))
    return cases, runs


def datasets_for(client: Any, family: str) -> list[dict[str, Any]]:
    rows = client.table("datasets").select("id,slug,name,window_start,window_end,benchmark_family").eq("benchmark_family", family).execute().data
    return sorted(rows, key=lambda d: (d.get("window_end") or "", d["slug"]))


# Each freshness cohort is its own frozen input list. Publishing it alongside
# the snapshot is what makes that snapshot re-runnable: the enrichment
# inputs CSV describes a different set of companies, so without this a reader
# can read a freshness result but cannot reproduce it.
INPUT_COLUMNS = [
    "candidate_id", "company_name", "company_domain", "ground_truth_stage",
    "ground_truth_announced_on", "ground_truth_amount", "ground_truth_currency",
    "ground_truth_total_raised", "official_source_url", "official_source_kind",
    "official_source_publisher", "official_published_at", "evidence_confidence",
    "evidence_quote", "review_status",
]


def write_inputs_csv(path: Path, cases: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INPUT_COLUMNS)
        writer.writeheader()
        for case in sorted(cases, key=lambda c: c["input_domain"]):
            ref = case.get("reference") or {}
            writer.writerow({
                "candidate_id": case["case_slug"],
                "company_name": case.get("input_name") or "",
                "company_domain": case["input_domain"],
                "ground_truth_stage": ref.get("latest_stage") or "",
                "ground_truth_announced_on": ref.get("latest_announced_on") or "",
                "ground_truth_amount": ref.get("latest_amount") if ref.get("latest_amount") is not None else "",
                "ground_truth_currency": ref.get("currency") or "",
                "ground_truth_total_raised": ref.get("total_raised") if ref.get("total_raised") is not None else "",
                "official_source_url": ref.get("official_source_url") or "",
                "official_source_kind": ref.get("official_source_kind") or "",
                "official_source_publisher": ref.get("official_source_publisher") or "",
                "official_published_at": ref.get("official_published_at") or "",
                "evidence_confidence": ref.get("evidence_confidence") or "",
                "evidence_quote": ref.get("evidence_quote") or "",
                "review_status": ref.get("review_status") or "",
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--enrichment-slug", default=None, help="Override the enrichment dataset; defaults to the only funding-enrichment dataset.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be written without writing.")
    args = parser.parse_args()

    client = create_client(os.environ["SNAPSHOT_SUPABASE_URL"], os.environ["SNAPSHOT_SUPABASE_SERVICE_ROLE_KEY"])

    enrichment_sets = datasets_for(client, FAMILY["enrichment"])
    if args.enrichment_slug:
        enrichment_sets = [d for d in enrichment_sets if d["slug"] == args.enrichment_slug]
    if len(enrichment_sets) != 1:
        raise RuntimeError(f"expected exactly one enrichment dataset, found {[d['slug'] for d in enrichment_sets]}")
    enrichment = enrichment_sets[0]
    freshness_sets = datasets_for(client, FAMILY["freshness"])
    if not freshness_sets:
        raise RuntimeError("no funding-freshness datasets found; has the split been promoted to this database?")

    e_cases, e_runs = load_dataset(client, enrichment)
    e_board = leaderboard(e_runs)

    snapshots, pooled_runs = [], []
    for dataset in freshness_sets:
        cases, runs = load_dataset(client, dataset)
        pooled_runs.extend(runs)
        label = (dataset.get("window_end") or dataset["slug"])[:7]
        path = FRESHNESS_DIR / f"{label}.json"
        payload = {
            "schema_version": SCHEMA_VERSION, "board": "freshness", "dataset_slug": dataset["slug"],
            "dataset_name": dataset["name"], "window": [dataset.get("window_start"), dataset.get("window_end")],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "case_count": len(cases), "cases": cases, "runs": runs, "leaderboard": leaderboard(runs),
        }
        snapshots.append({
            "slug": dataset["slug"], "label": label,
            "window": [dataset.get("window_start"), dataset.get("window_end")],
            "case_count": len(cases), "provider_count": len({r["provider_slug"] for r in runs}),
            "path": str(path.relative_to(ROOT)),
        })
        if not args.dry_run:
            FRESHNESS_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_inputs_csv(FRESHNESS_DIR / f"{label}-inputs.csv", cases)

    combined = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge": {"model": "gpt-5.6", "reasoning_effort": "medium", "policy": "docs/company-funding/llm-judge-v2.md"},
        "evaluated_fields": list(FIELDS),
        "boards": {
            "enrichment": {
                "dataset_slug": enrichment["slug"], "dataset_name": enrichment["name"],
                "window": [enrichment.get("window_start"), enrichment.get("window_end")],
                "description": "Rounds announced more than 30 days ago. Grows as freshness snapshots age in.",
                "stage_metric": "LLM-judged correct latest stages / the cases each provider was measured on",
                "case_count": len(e_cases),
                "providers": {r["provider_slug"]: r["provider_name"] for r in e_board},
                "cases": e_cases, "runs": e_runs, "leaderboard": e_board,
            },
            "freshness": {
                "description": "Rounds announced in the trailing 30 days, re-run each cycle. Pooled across the snapshots each provider took part in; per-snapshot cells live in the dated files.",
                "stage_metric": "LLM-judged correct latest stages / the cases each provider was measured on, pooled across snapshots",
                "providers": {r["provider_slug"]: r["provider_name"] for r in leaderboard(pooled_runs)},
                "snapshots": snapshots,
                "leaderboard": leaderboard(pooled_runs),
            },
        },
    }
    if not args.dry_run:
        OUTPUT.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "dry_run": args.dry_run, "output": str(OUTPUT.relative_to(ROOT)),
        "enrichment": {"slug": enrichment["slug"], "cases": len(e_cases), "runs": len(e_runs), "providers": len(e_board)},
        "freshness": {"snapshots": [s["label"] for s in snapshots], "pooled_runs": len(pooled_runs),
                      "providers": len(combined["boards"]["freshness"]["leaderboard"])},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
