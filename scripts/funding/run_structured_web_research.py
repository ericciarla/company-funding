#!/usr/bin/env python3
"""Compare structured web-research funding outputs from Parallel Tasks and Exa."""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data" / "funding" / "company-funding-benchmark-inputs-v1.csv"
DOMAINS = {"tanisbrush.com", "radai.com", "getunleash.io", "kuantom.com", "ramp.com"}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "latest_stage": {"type": ["string", "null"], "description": "Most recent funding stage; null if unavailable."},
        "latest_announced_on": {"type": ["string", "null"], "description": "Most recent funding announcement date in YYYY-MM-DD; null if unavailable."},
        "latest_amount": {"type": ["integer", "null"], "description": "Latest round amount in whole major-currency units, never millions or billions; null if undisclosed."},
        "currency": {"type": ["string", "null"], "description": "ISO 4217 currency of latest_amount; null if unavailable."},
        "total_raised": {"type": ["integer", "null"], "description": "Total funding raised in whole major-currency units; null if unavailable."},
        "funding_round_count": {"type": ["integer", "null"], "description": "Number of funding rounds; null if unavailable."},
    },
    "required": ["latest_stage", "latest_announced_on", "latest_amount", "currency", "total_raised", "funding_round_count"],
    "additionalProperties": False,
}


def funding_instruction(case: dict[str, str]) -> str:
    return f"""Research {case['company_name']} ({case['company_domain']}) and identify its most recent funding event.
Use company, investor, or company-issued wire sources where possible. Do not infer unknown fields; return null."""


def request_json(url: str, headers: dict[str, str], payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers=headers, method="POST" if payload is not None else "GET")
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def run_parallel(case: dict[str, str]) -> dict:
    headers = {"x-api-key": os.environ["PARALLEL_API_KEY"], "Content-Type": "application/json"}
    payload = {
        "input": {"company_name": case["company_name"], "company_website": case["company_domain"], "instruction": funding_instruction(case)},
        "processor": "core",
        "task_spec": {
            "input_schema": {"type": "json", "json_schema": {"type": "object", "properties": {"company_name": {"type": "string"}, "company_website": {"type": "string"}, "instruction": {"type": "string"}}, "required": ["company_name", "company_website", "instruction"]}},
            "output_schema": {"type": "json", "json_schema": OUTPUT_SCHEMA},
        },
    }
    created = request_json("https://api.parallel.ai/v1/tasks/runs", headers, payload)
    run_id = created["run_id"]
    for _ in range(36):
        try:
            result = request_json(f"https://api.parallel.ai/v1/tasks/runs/{run_id}/result", headers)
        except HTTPError as error:
            if error.code not in {202, 404}:
                raise
            result = None
        if result and (result.get("status") in {"completed", "succeeded"} or result.get("output")):
            return {"run_id": run_id, "created": created, "result": result}
        time.sleep(10)
    raise TimeoutError(f"Parallel Task {run_id} did not complete within six minutes")


def run_exa(case: dict[str, str]) -> dict:
    headers = {"x-api-key": os.environ["EXA_API_KEY"], "Content-Type": "application/json"}
    payload = {"query": funding_instruction(case), "type": "deep-reasoning", "output_schema": OUTPUT_SCHEMA}
    return request_json("https://api.exa.ai/search", headers, payload)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"parallel", "exa"}:
        raise SystemExit("Usage: run_structured_web_research_pilot.py [parallel|exa]")
    provider = sys.argv[1]
    env_key = "PARALLEL_API_KEY" if provider == "parallel" else "EXA_API_KEY"
    if not os.environ.get(env_key):
        raise RuntimeError(f"{env_key} is required")
    cases = [case for case in csv.DictReader(INPUT.open(newline="", encoding="utf-8")) if case["company_domain"] in DOMAINS]
    if len(cases) != 5:
        raise RuntimeError(f"Expected five pilot cases; found {len(cases)}")
    runner = run_parallel if provider == "parallel" else run_exa
    results = []
    if provider == "parallel":
        # The result endpoint blocks until the run completes. Keep this small
        # pilot sequential so each run is persisted even if a later call fails.
        for case in cases:
            raw = runner(case)
            results.append({"company": case["company_name"], "domain": case["company_domain"], "reference_stage": case["ground_truth_stage"], "reference_date": case["ground_truth_announced_on"], "raw": raw})
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(runner, case): case for case in cases}
            for future in as_completed(futures):
                case = futures[future]
                results.append({"company": case["company_name"], "domain": case["company_domain"], "reference_stage": case["ground_truth_stage"], "reference_date": case["ground_truth_announced_on"], "raw": future.result()})
    results.sort(key=lambda row: row["domain"])
    output = ROOT / "outputs" / f"{provider}-structured-funding-pilot-5.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
