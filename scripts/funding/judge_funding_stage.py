#!/usr/bin/env python3
"""Run the public v2 latest-stage judge against JSON records.

Usage:
  OPENAI_API_KEY=... python scripts/funding/judge_funding_stage.py records.json judgments.json

``records.json`` must be an object containing a ``records`` array. Each record
uses the public snapshot's case/run shape: record_id, ground_truth, and vendor.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from openai import OpenAI


PROMPT = """You are a strict evaluator for a company-funding benchmark. Evaluate each record independently.

Use only the supplied values. Do not research companies, infer facts, or use outside knowledge.
Ignore capitalization, underscores, hyphens, extra spaces, and the words \"round\" or \"financing\" when they do not change a funding type.

Rules:
1. Series A through Series H are strict: the vendor must state the same letter. A same-letter suffix does not change the Series: Series B matches B, B1, B2, B3, B+, B Plus, Series B, Series B+, and series_b_plus. A date or amount never rescues a wrong or missing Series letter. Seed, Pre-Seed, Venture, Private Equity, Debt, and unspecified funding rounds do not match a Series letter.
2. The following non-Series labels are equivalent, in either direction:
   - Seed, Seed Bridge, and Pre-Series A.
   - Private Equity, PE, PE Growth, Growth Investment, Growth Equity, Strategic Funding, Strategic Round, Strategic Investment, Corporate Investment, and Corporate Round.
   - Equity Crowdfunding, Grant, and Non-Equity Assistance.
3. Seed and Pre-Seed are distinct: neither matches the other. The Seed / Pre-Series A equivalence in rule 2 is the only exception involving Pre-Series A.
4. If ground truth is Early Stage, Seed and Pre-Seed vendor stages are correct.
5. If ground truth is Undisclosed, an Undisclosed or null/blank vendor stage is correct.
6. If ground truth stage is null or blank, every vendor answer is correct.
7. For every other non-Series ground-truth stage: accept a clearly equivalent stage. If stages are not equivalent, accept only if dates are both present and exactly identical, or amounts are both present and exactly numerically identical. Amounts are whole major-currency units; never use approximate equality.
8. Generic or vague labels (funding, funding round, venture, other, unknown, private financing, early-stage, structured financing) are not stage matches unless explicitly allowed above.

Return exactly one result for every input record. Copy its record_id exactly. Reasons must be concise and name the rule used.
"""

RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "record_id": {"type": "string"}, "scoreable": {"type": "boolean"},
            "correct": {"type": "boolean"},
            "decision_basis": {"type": "string", "enum": ["same_series_letter", "equivalent_stage", "exact_date_match", "exact_amount_match", "blank_ground_truth_pass", "incorrect"]},
            "reason": {"type": "string"},
        },
        "required": ["record_id", "scoreable", "correct", "decision_basis", "reason"],
    }}}, "required": ["results"],
}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: judge_funding_stage.py records.json judgments.json")
    source, destination = map(Path, sys.argv[1:])
    records = json.loads(source.read_text(encoding="utf-8"))["records"]
    response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).responses.create(
        model=os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.6"),
        reasoning={"effort": os.getenv("OPENAI_JUDGE_REASONING_EFFORT", "medium")},
        text={"verbosity": "low", "format": {"type": "json_schema", "name": "funding_stage_judgments", "strict": True, "schema": RESULT_SCHEMA}},
        max_output_tokens=12_000,
        input=[{"role": "developer", "content": PROMPT}, {"role": "user", "content": json.dumps({"records": records}, separators=(",", ":"))}],
    )
    result = json.loads(response.output_text)
    if {row["record_id"] for row in result["results"]} != {row["record_id"] for row in records}:
        raise RuntimeError("judge response did not return exactly one result per record")
    destination.write_text(json.dumps({"model": os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.6"), "reasoning_effort": os.getenv("OPENAI_JUDGE_REASONING_EFFORT", "medium"), **result}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
