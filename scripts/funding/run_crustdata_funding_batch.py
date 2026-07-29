#!/usr/bin/env python3
"""Submit and retrieve the 300-company Crustdata funding enrichment batch.

The batch API avoids individual-enrichment rate limits. Submission and every
poll response are saved locally before any later processing can occur.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data" / "funding" / "company-funding-benchmark-inputs-v1.csv"
STATE = ROOT / "data" / "funding" / "provider-runs-v2" / "crustdata-batch-state.json"
BASE_URL = "https://api.crustdata.com"
HEADERS = lambda: {
    "authorization": f"Bearer {os.environ['CRUSTDATA_API_KEY']}",
    "content-type": "application/json",
    "x-api-version": "2025-11-01",
}


def request_json(url: str, payload: dict | None = None) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=HEADERS(),
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"Crustdata HTTP {error.code}: {detail}") from error


def write_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "poll"])
    args = parser.parse_args()
    if not os.environ.get("CRUSTDATA_API_KEY"):
        raise RuntimeError("CRUSTDATA_API_KEY is required")
    if args.command == "submit":
        if STATE.exists():
            raise RuntimeError(f"Saved batch state already exists: {STATE}. Use poll; do not submit a duplicate batch.")
        cases = list(csv.DictReader(INPUT.open(newline="", encoding="utf-8")))
        domains = [case["company_domain"] for case in cases]
        if len(domains) != 300 or len(set(domains)) != 300:
            raise RuntimeError("Expected 300 unique benchmark domains")
        response = request_json(
            f"{BASE_URL}/batch/company/enrich",
            {"domains": domains, "fields": ["funding"], "chunk_size": 100},
        )
        state = {"submitted_at": datetime.now(UTC).isoformat(), "domains": domains, "submission": response}
        write_state(state)
        print(json.dumps(state, indent=2))
        return 0
    if not STATE.exists():
        raise RuntimeError("No saved submission state; run submit first.")
    state = json.loads(STATE.read_text())
    batch_id = state["submission"]["batch_id"]
    status = request_json(f"{BASE_URL}/batch/{batch_id}")
    state["last_polled_at"] = datetime.now(UTC).isoformat()
    state["status"] = status
    write_state(state)
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
