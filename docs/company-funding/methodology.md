# Methodology

## Cohort design

This is a GTM-oriented latest-funding cohort for account prioritization and qualification. It intentionally over-samples companies with known funding transitions, rather than estimating market-share prevalence. The frozen panel contains 300 domains: 134 events from 3–24 months before collection, 129 from 8–90 days, and 37 fresh company-issued announcements from the preceding seven days.

## Sourcing and validation

Candidate companies came from a time-windowed funding-transition index and were independently researched. A record was retained only with a direct company newsroom item, a company-issued wire announcement, or an equivalent primary source. The frozen input file preserves the source URL, date, stage, amount when disclosed, and evidence note. The recent cohort was discovered from current public funding news and required a verified company-domain identity. The 300-domain panel was frozen before provider scoring.

## Provider execution

Eleven providers were evaluated programmatically on the same company domain inputs. The original seven used documented company or funding endpoints; Exa and Parallel used the same structured funding-research request; Crustdata used documented company enrichment; and ZoomInfo used the GTM Studio `companies enrich` CLI with the funding fields. ZoomInfo requests were serial batches of ten domains with a two-second interval, and the batch latency is retained on each mapped row. Crunchbase was evaluated from a self-serve-plan CSV export matched to the same 300-company panel, not from an API request. Harmonic was evaluated from a supplied 300-record export identity-audited against that same panel; its returned website is retained as audit metadata rather than replacing the input domain. Both exports are included in correctness and coverage comparisons but intentionally have no request-latency or cost values.

Every completed programmatic call or exported record produced a local checkpoint with status, latency where applicable, failure reason, normalized funding fields, and relevant response paths. Literal vendor response bodies and export rows stay local and are excluded from public artifacts. The public builder projects checkpoint-format aliases (`latest_announced_on` → `latest_date`, `funding_round_count` → `round_count`) onto one normalized five-field contract. Existing checkpoints are skipped by default. Only explicitly selected retry statuses can be retried.

## Evaluation

The headline comparison is latest funding stage. The v2 release evaluates every provider cell with `gpt-5.6-terra` at medium reasoning effort, using only the supplied Ground Truth stage/date/amount and the normalized provider stage/date/amount. The exact executable prompt and structured response schema are public in [`judge_funding_stage.py`](../../scripts/funding/judge_funding_stage.py); every cell's decision basis and concise reason are retained in `data/latest-funding.json`.

Correct stage yield is LLM-judged correct latest stages divided by all 300 Ground Truth-reviewed companies. The policy handles documented equivalents (including same-letter Series suffixes, PE/growth, strategic-investment, Seed Bridge/Pre-Series A, and crowdfunding/grant variants), keeps Seed and Pre-Seed distinct, and permits exact date or amount evidence for other non-Series disagreements. Blank Ground Truth passes every vendor response; Undisclosed Ground Truth accepts an Undisclosed or blank vendor stage.

Latest date, latest amount, total raised, and funding-round count are retained as normalized outputs and contribute to the returned-data coverage metric, but are not headline-scored in this release.
