#!/usr/bin/env python3
"""Recompute every leaderboard from the committed cells; no API calls.

Rebuilds both boards and each dated freshness snapshot from the judge verdicts
already in the artifacts, using the same per-provider-denominator logic the
exporter and the site use. Running this should be a no-op on a healthy
artifact: if it changes anything, the published leaderboard did not follow from
the published cells.

--check reports drift without writing, which is the useful mode in CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_llm_judged_snapshot import FRESHNESS_DIR, OUTPUT, ROOT, leaderboard


def diff_rows(label: str, old: list[dict], new: list[dict]) -> list[str]:
    """Compare on the scored fields; ignore key order and absent extras."""
    keys = ("rank", "case_count", "snapshot_count", "cases_attempted", "cases_resolved",
            "eligible_stage_cases", "correct_stage_count", "stage_correct_yield_pct",
            "stage_fill_rate_pct", "stage_accuracy_when_present_pct",
            "funding_field_coverage_pct", "avg_funding_fields_returned", "resolution_rate_pct")
    by_slug = {row["provider_slug"]: row for row in old}
    drift = []
    for row in new:
        before = by_slug.get(row["provider_slug"])
        if before is None:
            drift.append(f"{label}: {row['provider_slug']} is new")
            continue
        for key in keys:
            if before.get(key) != row.get(key):
                drift.append(f"{label}/{row['provider_slug']}.{key}: {before.get(key)} -> {row.get(key)}")
    for slug in set(by_slug) - {row["provider_slug"] for row in new}:
        drift.append(f"{label}: {slug} disappeared")
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Report drift and exit non-zero; write nothing.")
    args = parser.parse_args()

    snapshot = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if snapshot.get("schema_version") != "3.0":
        raise RuntimeError(f"expected schema_version 3.0, found {snapshot.get('schema_version')}")

    drift: list[str] = []
    enrichment = snapshot["boards"]["enrichment"]
    rebuilt = leaderboard(enrichment["runs"])
    drift += diff_rows("enrichment", enrichment["leaderboard"], rebuilt)
    enrichment["leaderboard"] = rebuilt

    pooled_runs = []
    for entry in snapshot["boards"]["freshness"]["snapshots"]:
        path = ROOT / entry["path"]
        snap = json.loads(path.read_text(encoding="utf-8"))
        rebuilt_snap = leaderboard(snap["runs"])
        drift += diff_rows(entry["label"], snap["leaderboard"], rebuilt_snap)
        snap["leaderboard"] = rebuilt_snap
        pooled_runs.extend(snap["runs"])
        if not args.check:
            path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rebuilt_pooled = leaderboard(pooled_runs)
    drift += diff_rows("freshness/pooled", snapshot["boards"]["freshness"]["leaderboard"], rebuilt_pooled)
    snapshot["boards"]["freshness"]["leaderboard"] = rebuilt_pooled

    if not args.check:
        OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total = len(enrichment["runs"]) + len(pooled_runs)
    if drift:
        print(f"DRIFT: {len(drift)} field(s) did not match the committed leaderboard")
        for line in drift[:25]:
            print(f"   {line}")
        if len(drift) > 25:
            print(f"   ... and {len(drift) - 25} more")
        return 1 if args.check else 0
    print(f"recomputed {total} cells across both boards; no drift; network calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
