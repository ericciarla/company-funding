# Data contract

## Inputs and reference data

`data/funding/company-funding-inputs-v1.csv` is the frozen 300-domain panel. Each row has the company identity, recency and stage buckets, latest funding reference fields, and its primary-source metadata:

- `official_source_url`, `official_source_kind`, `official_source_publisher`, and `official_published_at`
- `ground_truth_stage`, `ground_truth_announced_on`, `ground_truth_amount`, `ground_truth_currency`, and `ground_truth_total_raised`
- `evidence_confidence`, `evidence_quote`, and `review_status`

The 300 records comprise 134 events from 3–24 months before collection, 129 events from 8–90 days, and 37 company-issued announcements from the preceding seven days. The list was frozen before provider scoring.

## Publication snapshot

`data/latest-funding.json` contains the exact 300 cases and 2,100 provider cells used by the public leaderboard. A run records only the normalized contract, status, latency, error, and funding-related response paths. It intentionally excludes literal vendor HTTP response bodies.

`stage_eligible`, `stage_returned`, and `stage_correct` are deterministic 0/1 judgments. Stage correctness is evaluated only when the reference stage maps to the canonical taxonomy.

## Canonical latest-stage taxonomy

The scorer maps labels to `pre_seed`, `seed`, `pre_series_a`, `pre_series_b`, `series_a` through `series_h`, `private_equity`, `growth_equity`, `strategic_or_corporate`, `equity_crowdfunding`, `angel`, `venture_unspecified`, `convertible_note`, `debt_or_credit`, `grant_or_non_equity`, `pre_ipo`, and `post_ipo`.

Specific labels such as `Series B1` map to their parent stage. Vague labels such as `early stage`, `funding`, or `undisclosed` do not create a scored stage label.
