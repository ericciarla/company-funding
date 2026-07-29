# Methodology

## Cohort design

This is a GTM-oriented latest-funding cohort for account prioritization and qualification. It intentionally over-samples companies with known funding transitions, rather than estimating market-share prevalence. The frozen panel contains 300 domains: 134 events from 3–24 months before collection, 129 from 8–90 days, and 37 fresh company-issued announcements from the preceding seven days.

## Sourcing and validation

Candidate companies came from a time-windowed funding-transition index and were independently researched. A record was retained only with a direct company newsroom item, a company-issued wire announcement, or an equivalent primary source. The frozen input file preserves the source URL, date, stage, amount when disclosed, and evidence note. The recent cohort was discovered from current public funding news and required a verified company-domain identity. The 300-domain panel was frozen before provider scoring.

## Provider execution

Ten providers were evaluated programmatically on the same company domain inputs. The original seven used documented company or funding endpoints; Exa and Parallel used the same structured funding-research request; Crustdata used documented company enrichment. Crunchbase was evaluated from a self-serve-plan CSV export matched to the same 300-company panel, not from an API request. Its result is included in accuracy and coverage comparisons but intentionally has no request-latency value.

Every completed programmatic call or exported record produced a local checkpoint with status, latency where applicable, failure reason, normalized funding fields, and relevant response paths. Literal vendor response bodies and export rows stay local and are excluded from public artifacts. The public builder projects checkpoint-format aliases (`latest_announced_on` → `latest_date`, `funding_round_count` → `round_count`) onto one normalized five-field contract. Existing checkpoints are skipped by default. Only explicitly selected retry statuses can be retried.

## Evaluation

The headline comparison is latest funding stage. Source and provider labels are deterministically normalized into the canonical taxonomy documented in [DATA.md](../../DATA.md). Correct stage yield is correct canonical latest stages divided by companies with an available specific, source-verified stage label. Missing and incorrect provider stages lower yield. Missing or vague reference-stage labels are excluded from the denominator.

Latest date, latest amount, total raised, and funding-round count are retained as normalized outputs and contribute to the returned-data coverage metric, but are not headline-scored in this release.
