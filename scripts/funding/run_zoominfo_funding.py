#!/usr/bin/env python3
"""Run ZoomInfo GTM company enrichment for the frozen funding cohort.

The logged-in ``gtm`` CLI accepts a JSON file of domains. This runner sends
serial 10-domain batches (with a two-second interval), retains each batch's
response locally, and writes one resumable checkpoint per company. Literal
responses are ignored by git and never enter the public snapshot.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data/funding/company-funding-inputs-v1.csv"
RAW = ROOT / "data/funding/provider-runs-v2/raw/zoominfo"
BATCHES = ROOT / "data/funding/provider-runs-v2/raw/zoominfo-batches"
FIELDS = ["companyFunding", "recentFundingAmount", "recentFundingDate", "totalFundingAmount"]
CHUNK_SIZE = 10


def stamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def major_usd(value: Any) -> int | float | None:
    """The CLI returns funding amounts in USD thousands; public values are USD."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value)) * 1000
    except (InvalidOperation, ValueError):
        return None
    return int(result) if result == result.to_integral_value() else float(result)


def normalized(company: dict[str, Any]) -> dict[str, Any]:
    rounds = sorted((row for row in company.get("companyFunding") or [] if isinstance(row, dict)), key=lambda row: str(row.get("date") or ""), reverse=True)
    latest = rounds[0] if rounds else {}
    date = (latest.get("date") or "").split("T", 1)[0] or None
    amount, total = major_usd(latest.get("amount")), major_usd(company.get("totalFundingAmount"))
    return {"latest_stage": latest.get("type"), "latest_announced_on": date, "latest_date": date,
            "latest_amount": amount, "currency": "USD" if amount is not None or total is not None else None,
            "total_raised": total, "funding_round_count": len(rounds) or None, "round_count": len(rounds) or None}


def final(path: Path) -> bool:
    try:
        return json.loads(path.read_text()).get("status") in {"ok", "not_found"}
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def call(cases: list[dict[str, str]]) -> tuple[dict[str, Any], int, str | None]:
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump([{"domain": case["company_domain"]} for case in cases], handle)
        handle.flush()
        process = subprocess.run(["gtm", "companies", "enrich", "--file", handle.name, "--fields", *FIELDS, "--format", "json"], capture_output=True, text=True, check=False, timeout=180)
    latency = round((time.perf_counter() - started) * 1000)
    if process.returncode:
        return {}, latency, (process.stderr or process.stdout).strip() or f"gtm exited {process.returncode}"
    try:
        return json.loads(process.stdout), latency, None
    except json.JSONDecodeError as error:
        return {}, latency, f"invalid JSON response: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Make paid CLI calls; default prints the resumable plan.")
    parser.add_argument("--interval-seconds", type=float, default=2)
    args = parser.parse_args()
    cases = list(csv.DictReader(INPUT.open(encoding="utf-8", newline="")))
    if len(cases) != 300 or len({case["company_domain"] for case in cases}) != 300:
        raise RuntimeError("expected the frozen 300-domain cohort")
    pending = [case for case in cases if not final(RAW / f"{case['company_domain']}.json")]
    print(json.dumps({"cohort": len(cases), "saved": len(cases) - len(pending), "pending": len(pending), "requests": (len(pending) + 9) // 10, "batch_size": CHUNK_SIZE, "serial": True, "interval_seconds": args.interval_seconds, "run": args.run}))
    if not args.run:
        return 0
    for offset in range(0, len(pending), CHUNK_SIZE):
        group = pending[offset:offset + CHUNK_SIZE]
        try:
            payload, latency, error = call(group)
            batch_file = BATCHES / f"batch-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
            save(batch_file, {"requested_domains": [case["company_domain"] for case in group], "completed_at": stamp(), "latency_ms": latency, "response": payload, "error": error})
            for index, case in enumerate(group, start=1):
                response = payload.get(f"company_{index}") if payload else {}
                company = response.get("data") if isinstance(response, dict) else {}
                success = bool(isinstance(response, dict) and response.get("success") and company)
                save(RAW / f"{case['company_domain']}.json", {"provider": "zoominfo", "case_slug": case["candidate_id"], "input": {"company_name": case["company_name"], "domain": case["company_domain"]}, "source": "zoominfo_gtm_companies_enrich", "completed_at": stamp(), "status": "error" if error else ("ok" if success else "not_found"), "failure_reason": error or (None if success else "ZoomInfo returned no company match"), "latency_ms": latency, "batch_response_file": str(batch_file.relative_to(ROOT)), "normalized": normalized(company) if success else {}, "raw": response})
        except Exception as error:
            for case in group:
                save(RAW / f"{case['company_domain']}.json", {"provider": "zoominfo", "case_slug": case["candidate_id"], "input": {"company_name": case["company_name"], "domain": case["company_domain"]}, "source": "zoominfo_gtm_companies_enrich", "completed_at": stamp(), "status": "error", "failure_reason": f"{type(error).__name__}: {error}", "latency_ms": None, "normalized": {}})
        if offset + len(group) < len(pending):
            time.sleep(args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
