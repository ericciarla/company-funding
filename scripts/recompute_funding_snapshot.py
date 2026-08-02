#!/usr/bin/env python3
"""Recompute the v2 leaderboard from committed LLM verdicts; no API calls."""
from __future__ import annotations

import json
from pathlib import Path

from export_llm_judged_snapshot import OUTPUT, leaderboard


def main() -> int:
    snapshot = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if snapshot.get("schema_version") != "2.0":
        raise RuntimeError("expected the LLM-judged v2 snapshot")
    snapshot["leaderboard"] = leaderboard(snapshot["cases"], snapshot["runs"])
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recomputed {len(snapshot['runs'])} runs; network calls: 0")


if __name__ == "__main__":
    raise SystemExit(main())
