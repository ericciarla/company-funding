# Methodology

## Cohort design

This is a GTM-oriented latest-funding benchmark for account prioritization and qualification. It intentionally over-samples companies with known funding transitions, rather than estimating market-share prevalence.

It is split into two boards on the announcement date of the round:

- **Enrichment** — rounds announced more than 30 days ago. One growing historical cohort.
- **Freshness** — rounds announced in the trailing 30 days, built fresh each cycle as a dated snapshot and re-run against every runnable vendor.

The split exists because the two measure different things. A vendor with a strong historical database can lag badly on rounds announced this week, and a news-driven vendor can be the reverse. A single blended score hid that difference entirely.

Freshness is a rolling measurement: results pool across the snapshots a vendor took part in, and vendors join at different cycles, so each row publishes its own case count and snapshot count.

## Grouping by mechanism

Both boards subdivide the roster by how a provider produces its answer: **long running agent APIs** dispatch an agent that researches each company at request time, **web search APIs** query an index and extract the answer from it, and **GTM data providers** return a stored record from a maintained database. A single ranked list quietly compares things that are not substitutes, because a two-minute research agent and a 200ms database lookup can post the same accuracy while being different purchases with different costs and failure modes.

The grouping is a reading aid, not a scoring rule. Every arm is asked the same question about the same companies and judged by the same policy, so the rows stay directly comparable and nothing is excluded or weighted differently. The distinction is about mechanism rather than vendor, so Exa and Parallel each appear in two groups: Exa's Agent API and Parallel's Task API dispatch an agent that researches the company, while Exa's two /search arms and Parallel's Responses API resolve the question against an index.

## Sourcing and validation

Candidate companies came from a time-windowed funding-transition index and were independently researched. A record was retained only with a direct company newsroom item, a company-issued wire announcement, or an equivalent primary source. The frozen input file preserves the source URL, date, stage, amount when disclosed, and evidence note. The recent cohort was discovered from current public funding news and required a verified company-domain identity. The 300-domain panel was frozen before provider scoring.

## Provider execution

The programmatic providers were evaluated on the same company domain inputs. The original seven used documented company or funding endpoints; Exa, Parallel, Seltz and Firecrawl used the same structured funding-research request; Crustdata used documented company enrichment; and ZoomInfo used the GTM Studio `companies enrich` CLI with the funding fields.

Three vendors are measured on more than one endpoint, and each arm changes exactly one thing while the instruction and the output schema stay byte-identical. Exa runs `/search` at `type=deep-reasoning` and at `type=instant`, plus its Agent API, which is a different mechanism rather than another search setting; Parallel runs the Task API and the Responses API; Seltz runs its `companies` and `news` scopes. That parity is asserted by contract tests beside the runner rather than left to review, so a difference in score is attributable to the varied parameter alone. Firecrawl's agent endpoint bills dynamic credits per run, so its cost is summed from the `creditsUsed` each response reports rather than modeled from a rate card. Exa's Agent API is priced per request by effort and the runner pins it, because the API default of `effort=auto` meters up to $5 per run.

Every completed programmatic call or exported record produced a local checkpoint with status, latency where applicable, failure reason, normalized funding fields, and relevant response paths. Literal vendor response bodies and export rows stay local and are excluded from public artifacts. The public builder projects checkpoint-format aliases (`latest_announced_on` → `latest_date`, `funding_round_count` → `round_count`) onto one normalized five-field contract. Existing checkpoints are skipped by default. Only explicitly selected retry statuses can be retried.

## Evaluation

The headline comparison is latest funding stage. The v2 release evaluates every provider cell with `gpt-5.6-terra` at medium reasoning effort, using only the supplied Ground Truth stage/date/amount and the normalized provider stage/date/amount. The exact executable prompt and structured response schema are public in [`judge_funding_stage.py`](../../scripts/funding/judge_funding_stage.py); every cell's decision basis and concise reason are retained in `data/latest-funding.json`.

Correct stage yield is LLM-judged correct latest stages divided by the Ground Truth-reviewed companies that provider was measured on. Denominators differ per provider by design: a vendor added later is measured on more of the enrichment cohort than one added earlier, and vendors join freshness at different snapshots. The policy handles documented equivalents (including same-letter Series suffixes, PE/growth, strategic-investment, Seed Bridge/Pre-Series A, and crowdfunding/grant variants), keeps Seed and Pre-Seed distinct, and permits exact date or amount evidence for other non-Series disagreements. Blank Ground Truth passes every vendor response; Undisclosed Ground Truth accepts an Undisclosed or blank vendor stage.

Latest date, latest amount, total raised, and funding-round count are retained as normalized outputs and contribute to the returned-data coverage metric, but are not headline-scored in this release.
