# Data contract

## Inputs and reference data

`data/funding/company-funding-inputs-v1.csv` is the frozen 300-domain panel. Each row has the company identity, recency and stage buckets, latest funding reference fields, and its primary-source metadata:

- `official_source_url`, `official_source_kind`, `official_source_publisher`, and `official_published_at`
- `ground_truth_stage`, `ground_truth_announced_on`, `ground_truth_amount`, `ground_truth_currency`, and `ground_truth_total_raised`
- `evidence_confidence`, `evidence_quote`, and `review_status`

The 300 records comprise 134 events from 3–24 months before collection, 129 events from 8–90 days, and 37 company-issued announcements from the preceding seven days. The list was frozen before provider scoring.

## Publication snapshot

`data/latest-funding.json` contains the exact 300 cases and 3,600 provider cells used by the public leaderboard: eleven programmatic providers and Crunchbase's exported dataset. A run records only the normalized contract, status, latency where applicable, safe audit metadata, and the LLM judgment. It intentionally excludes literal vendor HTTP response bodies and Crunchbase export rows.

The public schema stays stable across checkpoint formats. `latest_announced_on` is projected to `latest_date`, and `funding_round_count` to `round_count`, before publication. Crunchbase is marked with source `csv_export` and has `latency_ms: null`; it must not be compared in request-latency rankings.

`stage_eligible`, `stage_returned`, and `stage_correct` are 0/1 metric values. Every run additionally contains `metrics.llm_judge`, with the GPT-5.6 Terra model/policy, decision basis, and concise reason used for the final stage verdict. All 300 Ground Truth-reviewed companies are eligible in v2.

## Canonical latest-stage taxonomy

The scorer maps labels to `pre_seed`, `seed`, `pre_series_a`, `pre_series_b`, `series_a` through `series_h`, `private_equity`, `growth_equity`, `strategic_or_corporate`, `equity_crowdfunding`, `angel`, `venture_unspecified`, `convertible_note`, `debt_or_credit`, `grant_or_non_equity`, `pre_ipo`, and `post_ipo`.

The v2 judgment policy is authoritative for scoring and is published in [`docs/company-funding/llm-judge-v2.md`](docs/company-funding/llm-judge-v2.md). It treats same-letter Series suffixes as a match, preserves the Seed/Pre-Seed distinction, specifies approved equivalence groups, and allows exact date or amount evidence for other non-Series disagreements.
