#!/usr/bin/env python3
"""Run ZoomInfo company enrichment for the frozen 300-company funding cohort.

This runner sends one ZoomInfo request for each ten-domain batch, records that
complete batch response and latency, and maps it to individual case rows.
Existing successful rows are skipped, making interrupted runs safe to resume.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data" / "funding" / "company-funding-benchmark-inputs-v1.csv"
RAW = ROOT / "data" / "funding" / "provider-runs-v3" / "raw" / "zoominfo"
BATCH_RAW = ROOT / "data" / "funding" / "provider-runs-v3" / "raw" / "zoominfo-batches"
CHUNK_SIZE = 10
FIELDS = [
    "companyFunding", "recentFundingAmount", "recentFundingDate",
    "totalFundingAmount",
]


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def final(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        saved = json.loads(path.read_text())
        # An early parser validation run saved the CLI's single-row envelope
        # without unwrapping ``company_1``. Re-run it rather than treating its
        # false no-match result as final.
        if isinstance((saved.get("raw") or {}).get("company_1"), dict):
            return False
        return saved.get("status") in {"ok", "not_found"}
    except json.JSONDecodeError:
        return False


def latest_round(rounds: object) -> tuple[dict[str, Any], int]:
    rows = [row for row in rounds or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return (rows[0] if rows else {}), len(rows)


def usd_thousands_to_major_units(value: object) -> int | float | None:
    """ZoomInfo funding amounts are USD thousands; benchmark amounts are USD."""
    if value is None or isinstance(value, bool):
        return None
    try:
        converted = Decimal(str(value)) * 1000
    except (InvalidOperation, ValueError):
        return None
    return int(converted) if converted == converted.to_integral_value() else float(converted)


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    latest, count = latest_round(data.get("companyFunding"))
    latest_amount = usd_thousands_to_major_units(latest.get("amount"))
    total_raised = usd_thousands_to_major_units(data.get("totalFundingAmount"))
    latest_date = (latest.get("date") or "").split("T", 1)[0] or None
    return {
        "latest_stage": latest.get("type"),
        # Keep both aliases: the stage judge consumes latest_announced_on,
        # while shared field-coverage presentation consumes latest_date.
        "latest_announced_on": latest_date,
        "latest_date": latest_date,
        "latest_amount": latest_amount,
        "currency": "USD" if latest_amount is not None or total_raised is not None else None,
        "total_raised": total_raised,
        "funding_round_count": count or None,
        "round_count": count or None,
    }


def row(case: dict[str, str], response: dict[str, Any], latency_ms: int, failure_reason: str | None = None, batch_file: str | None = None) -> dict[str, Any]:
    data = response.get("data") or {}
    success = bool(response.get("success")) and bool(data)
    return {
        "provider": "zoominfo", "case_slug": case["candidate_id"],
        "input": {"company_name": case["company_name"], "domain": case["company_domain"]},
        "source": "zoominfo_gtm_companies_enrich", "completed_at": now(),
        "status": "error" if failure_reason else ("ok" if success else "not_found"),
        "failure_reason": failure_reason or (None if success else "ZoomInfo returned no company match"),
        "latency_ms": latency_ms,
        "batch_response_file": batch_file,
        "normalized": normalize(data) if success else {},
        "raw": response,
    }


def invoke(cases: list[dict[str, str]]) -> tuple[dict[str, Any], int, str | None]:
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump([{"domain": case["company_domain"]} for case in cases], handle)
        handle.flush()
        result = subprocess.run(
            ["gtm", "companies", "enrich", "--file", handle.name, "--fields", *FIELDS, "--format", "json"],
            check=False, capture_output=True, text=True, timeout=180,
        )
    elapsed = round((time.perf_counter() - started) * 1000)
    if result.returncode:
        return {}, elapsed, (result.stderr or result.stdout).strip() or f"gtm exited {result.returncode}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return {}, elapsed, f"invalid JSON response: {error}"
    if not isinstance(payload, dict):
        return {}, elapsed, "invalid non-object CLI response"
    return payload, elapsed, None


def main() -> int:
    global RAW, BATCH_RAW
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Make live ZoomInfo calls; otherwise print the plan.")
    parser.add_argument("--refresh-normalized", action="store_true", help="Rebuild normalized fields from saved raw responses; makes no API calls.")
    parser.add_argument("--limit", type=int, help="Only process this many pending domains.")
    parser.add_argument("--max-workers", type=int, default=1, help="Must remain 1: ZoomInfo batches run serially.")
    parser.add_argument("--request-interval-seconds", type=float, default=2, help="Pause between serial 10-domain API calls.")
    # Freshness snapshots are their own cohorts, so input, output and expected
    # size are arguments rather than the frozen 300-domain enrichment input.
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--batch-dir", type=Path, default=BATCH_RAW)
    parser.add_argument("--expect-cases", type=int, default=None)
    args = parser.parse_args()
    # Resolve to absolute: cells record the batch file path relative to ROOT,
    # and a relative --batch-dir makes that relative_to() throw *after* the
    # paid API call has already been made, turning a good response into a
    # recorded error. Same failure this repo hit in the publish script.
    RAW, BATCH_RAW = args.raw_dir.resolve(), args.batch_dir.resolve()
    cases = list(csv.DictReader(args.input.open(newline="", encoding="utf-8")))
    if not cases:
        raise RuntimeError(f"{args.input} has no rows")
    if args.expect_cases is not None and (len(cases) != args.expect_cases or len({case["company_domain"] for case in cases}) != args.expect_cases):
        raise RuntimeError(f"expected exactly {args.expect_cases} distinct funding inputs, found {len(cases)}")
    if args.refresh_normalized:
        refreshed = 0
        for case in cases:
            path = RAW / f"{case['company_domain']}.json"
            if not path.exists():
                continue
            saved = json.loads(path.read_text())
            if saved.get("status") == "ok":
                saved["normalized"] = normalize((saved.get("raw") or {}).get("data") or {})
                write(path, saved)
                refreshed += 1
        print(json.dumps({"refreshed": refreshed, "source": "saved_zoominfo_raw", "network_calls": 0}))
        return 0
    pending = [case for case in cases if not final(RAW / f"{case['company_domain']}.json")]
    if args.limit is not None:
        pending = pending[:args.limit]
    if args.max_workers != 1:
        raise RuntimeError("ZoomInfo batches must run serially; use --max-workers 1")
    requests = (len(pending) + CHUNK_SIZE - 1) // CHUNK_SIZE
    plan = {"cohort": len(cases), "already_saved": len(cases) - len([case for case in cases if not final(RAW / f"{case['company_domain']}.json")]), "pending": len(pending), "requests": requests, "batch_size": CHUNK_SIZE, "max_workers": args.max_workers, "request_interval_seconds": args.request_interval_seconds, "run": args.run}
    print(json.dumps(plan), flush=True)
    if not args.run:
        return 0
    for batch_index, offset in enumerate(range(0, len(pending), CHUNK_SIZE), start=1):
        group = pending[offset:offset + CHUNK_SIZE]
        try:
            response, latency_ms, failure_reason = invoke(group)
            batch_path = BATCH_RAW / f"batch-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
            write(batch_path, {"requested_domains": [case["company_domain"] for case in group], "completed_at": now(), "latency_ms": latency_ms, "response": response, "error": failure_reason})
            batch_file = str(batch_path.relative_to(ROOT))
            for item_index, case in enumerate(group, start=1):
                item = response.get(f"company_{item_index}") if response else {}
                write(RAW / f"{case['company_domain']}.json", row(case, item if isinstance(item, dict) else {}, latency_ms, failure_reason, batch_file))
        except Exception as error:
            for case in group:
                write(RAW / f"{case['company_domain']}.json", {
                    "provider": "zoominfo", "case_slug": case["candidate_id"],
                    "input": {"company_name": case["company_name"], "domain": case["company_domain"]},
                    "source": "zoominfo_gtm_companies_enrich", "completed_at": now(),
                    "status": "error", "failure_reason": f"{type(error).__name__}: {error}", "latency_ms": None, "normalized": {},
                })
        completed = min(offset + len(group), len(pending))
        print(json.dumps({"batch": batch_index, "of": requests, "completed": completed, "of_pending": len(pending)}), flush=True)
        if completed < len(pending):
            time.sleep(args.request_interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
