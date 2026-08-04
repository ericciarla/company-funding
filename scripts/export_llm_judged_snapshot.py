#!/usr/bin/env python3
"""Export the public v2 snapshot without literal vendor response bodies.

Requires SNAPSHOT_SUPABASE_URL and SNAPSHOT_SUPABASE_SERVICE_ROLE_KEY.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/latest-funding.json"
DATASET_SLUG = "company-funding-enrichment-v2-llm-judge"
PROVIDERS = {"fiber": "Fiber", "predictleads": "PredictLeads", "apollo": "Apollo", "people-data-labs": "People Data Labs", "ocean": "Ocean.io", "explorium": "Explorium", "company-enrich": "CompanyEnrich", "crunchbase": "Crunchbase", "exa": "Exa", "parallel": "Parallel", "crustdata": "Crustdata", "zoominfo": "ZoomInfo", "harmonic": "Harmonic"}
FIELDS = ("latest_stage", "latest_date", "latest_amount", "total_raised", "round_count")


def fetch(client: Any, table: str, dataset_id: str, fields: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, 10_000, 1_000):
        page = client.table(table).select(fields).eq("dataset_id", dataset_id).range(offset, offset + 999).execute().data
        rows.extend(page)
        if len(page) < 1_000:
            return rows
    raise RuntimeError(f"pagination overflow for {table}")


def present(value: Any) -> bool:
    return value not in (None, "")


def leaderboard(cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for slug, name in PROVIDERS.items():
        provider = [run for run in runs if run["provider_slug"] == slug]
        eligible = sum(run["metrics"]["stage_eligible"] for run in provider)
        returned = sum(run["metrics"]["stage_returned"] for run in provider)
        correct = sum(run["metrics"]["stage_correct"] for run in provider)
        fields = sum(sum(present(run["normalized"].get(field)) for field in FIELDS) for run in provider)
        resolved = sum(run["status"] == "ok" for run in provider)
        rows.append({"provider_slug": slug, "provider_name": name, "total_cases": len(cases), "cases_attempted": len(provider), "cases_resolved": resolved, "resolution_rate_pct": round(100 * resolved / len(cases), 2), "eligible_stage_cases": eligible, "correct_stage_count": correct, "stage_correct_yield_pct": round(100 * correct / eligible, 2), "stage_fill_rate_pct": round(100 * returned / eligible, 2), "stage_accuracy_when_present_pct": round(100 * correct / returned, 2) if returned else None, "funding_field_coverage_pct": round(100 * fields / (len(provider) * len(FIELDS)), 2), "avg_funding_fields_returned": round(fields / len(provider), 2)})
    rows.sort(key=lambda row: (-row["stage_correct_yield_pct"], -row["resolution_rate_pct"], row["provider_slug"]))
    for rank, row in enumerate(rows, 1): row["rank"] = rank
    return rows


def main() -> None:
    client = create_client(os.environ["SNAPSHOT_SUPABASE_URL"], os.environ["SNAPSHOT_SUPABASE_SERVICE_ROLE_KEY"])
    dataset = client.table("datasets").select("id,slug,name").eq("slug", DATASET_SLUG).single().execute().data
    source_cases = fetch(client, "funding_cases", dataset["id"], "*")
    source_runs = fetch(client, "funding_runs", dataset["id"], "id,case_id,status,normalized_response,audit_response,latency_ms,cost_units,cost_unit,error,queried_at,providers(slug,name)")
    if len(source_cases) != 300 or len(source_runs) != 3_900:
        raise RuntimeError(f"unexpected source counts: {len(source_cases)} cases, {len(source_runs)} runs")
    case_by_id = {case["id"]: case for case in source_cases}
    metrics_by_run: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for start in range(0, len(source_runs), 100):
        for metric in client.table("funding_run_metrics").select("run_id,metric_name,metric_value,detail").in_("run_id", [run["id"] for run in source_runs[start:start + 100]]).execute().data:
            metrics_by_run[metric["run_id"]][metric["metric_name"]] = metric
    cases = []
    for case in source_cases:
        attributes, metadata = case.get("reference_attributes") or {}, case.get("source_metadata") or {}
        cases.append({"case_slug": case["case_slug"], "input_name": case.get("input_name"), "input_domain": case["input_domain"], "recency_bucket": case.get("recency_bucket"), "stage_bucket": case.get("stage_bucket"), "reference": {**attributes, **{key: metadata.get(key) for key in ("official_source_url", "official_source_kind", "official_source_publisher", "official_published_at", "evidence_confidence", "evidence_quote", "review_status")}}})
    runs = []
    for source in source_runs:
        normalized, metrics, audit = source.get("normalized_response") or {}, metrics_by_run[source["id"]], source.get("audit_response") or {}
        if set(metrics) != {"resolved", "stage_eligible", "stage_returned", "stage_correct", "stage_llm_judge"}:
            raise RuntimeError(f"incomplete metrics for {source['id']}")
        runs.append({"case_slug": case_by_id[source["case_id"]]["case_slug"], "provider_slug": source["providers"]["slug"], "provider_name": source["providers"]["name"], "status": source["status"], "latency_ms": source.get("latency_ms"), "cost_units": source.get("cost_units"), "cost_unit": source.get("cost_unit"), "error": source.get("error"), "queried_at": source.get("queried_at"), "normalized": {"latest_stage": normalized.get("latest_stage"), "latest_date": normalized.get("latest_date") or normalized.get("latest_announced_on"), "latest_amount": normalized.get("latest_amount"), "total_raised": normalized.get("total_raised"), "round_count": normalized.get("round_count") or normalized.get("funding_round_count")}, "audit": {key: audit.get(key) for key in ("source", "funding_related_paths", "prior_attempt_count", "failure_reason")}, "metrics": {"stage_eligible": metrics["stage_eligible"]["metric_value"], "stage_returned": metrics["stage_returned"]["metric_value"], "stage_correct": metrics["stage_correct"]["metric_value"], "llm_judge": metrics["stage_llm_judge"].get("detail") or {}}})
    snapshot = {"schema_version": "2.0", "dataset_slug": dataset["slug"], "dataset_name": dataset["name"], "status": "complete", "generated_at": datetime.now(timezone.utc).isoformat(), "case_count": len(cases), "providers": PROVIDERS, "evaluated_fields": list(FIELDS), "judge": {"model": "gpt-5.6", "reasoning_effort": "medium", "policy": "docs/company-funding/llm-judge-v2.md"}, "stage_metric": "LLM-judged latest funding stage correctness / 300 Ground Truth-reviewed companies", "case_counts_by_recency_bucket": dict(sorted(Counter(case["recency_bucket"] for case in cases).items())), "cases": sorted(cases, key=lambda case: case["case_slug"]), "runs": sorted(runs, key=lambda run: (run["case_slug"], run["provider_slug"]))}
    snapshot["leaderboard"] = leaderboard(snapshot["cases"], snapshot["runs"])
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(cases)} cases, {len(runs)} runs")


if __name__ == "__main__":
    main()
