# Data contract

## Inputs and reference data

`data/funding/company-funding-inputs-v1.csv` is the frozen enrichment panel. Each row has the company identity, recency and stage buckets, latest funding reference fields, and its primary-source metadata:

- `official_source_url`, `official_source_kind`, `official_source_publisher`, and `official_published_at`
- `ground_truth_stage`, `ground_truth_announced_on`, `ground_truth_amount`, `ground_truth_currency`, and `ground_truth_total_raised`
- `evidence_confidence`, `evidence_quote`, and `review_status`

The list was frozen before provider scoring. Each freshness snapshot has its own frozen input list covering its 30-day window, so a snapshot is reproducible from its own inputs rather than from a shared panel.

## Publication snapshot

`data/latest-funding.json` is `schema_version` 3.0 and contains both boards under `boards`:

- `boards.enrichment` — `cases`, `runs` and `leaderboard` for rounds older than 30 days.
- `boards.freshness` — the pooled `leaderboard` plus a `snapshots` manifest. Each entry names a dated file under `data/freshness/` holding that snapshot's own cases, runs and leaderboard. Cells live in the dated files rather than the combined one, so the combined file stays bounded as snapshots accumulate.

Every leaderboard row carries `case_count` and `snapshot_count`: a provider is scored against the companies it was actually measured on, not a board-wide total. A run records only the normalized contract, status, latency where applicable, safe audit metadata, and the LLM judgment. It intentionally excludes literal vendor HTTP response bodies and source-export rows.

The public schema stays stable across checkpoint formats. `latest_announced_on` is projected to `latest_date`, and `funding_round_count` to `round_count`, before publication. Crunchbase is marked with source `csv_export` and has `latency_ms: null`; it must not be compared in request-latency rankings.

`stage_eligible`, `stage_returned`, and `stage_correct` are 0/1 metric values. Every run additionally contains `metrics.llm_judge`, with the GPT-5.6 model/policy, decision basis, and concise reason used for the final stage verdict. Every Ground Truth-reviewed company a provider was measured on is eligible.

`stage_correct` and `stage_returned` are independent, and a run can be correct without having returned anything: the judgment policy passes any vendor answer where Ground Truth is blank, and accepts a blank answer where Ground Truth is Undisclosed. Anything deriving an accuracy-when-present figure must therefore use `min(stage_correct, stage_returned)` as its numerator over `stage_returned`. Summing raw `stage_correct` over `stage_returned` yields more than 100% wherever a cohort contains blank Ground Truth, which is what `stage_accuracy_when_present_pct` on each leaderboard row is computed to avoid. The headline `stage_correct_yield_pct` and `stage_fill_rate_pct` both divide by `stage_eligible` and are unaffected. Because Crunchbase and Harmonic are reviewed exports, their latency and cost are null rather than inferred. An export carries no query moment relative to an announcement, so whether it can join a freshness snapshot depends on obtaining a dated export for that window.

## Canonical latest-stage taxonomy

The scorer maps labels to `pre_seed`, `seed`, `pre_series_a`, `pre_series_b`, `series_a` through `series_h`, `private_equity`, `growth_equity`, `strategic_or_corporate`, `equity_crowdfunding`, `angel`, `venture_unspecified`, `convertible_note`, `debt_or_credit`, `grant_or_non_equity`, `pre_ipo`, and `post_ipo`.

The v2 judgment policy is authoritative for scoring and is published in [`docs/company-funding/llm-judge-v2.md`](docs/company-funding/llm-judge-v2.md). It treats same-letter Series suffixes as a match, preserves the Seed/Pre-Seed distinction, specifies approved equivalence groups, and allows exact date or amount evidence for other non-Series disagreements.
