# Company Funding Benchmark

Open data and reproducible runner code for the [OpenBenchmarks Company Funding Benchmark](https://openbenchmarks.com/company-funding).

The frozen release compares ten programmatic providers plus Crunchbase's exported dataset on the same 300 company domains. It is designed for GTM account prioritization and qualification: companies with known funding transitions are intentionally over-sampled so that the benchmark tests an actionable signal rather than mostly empty records.

## Evaluated fields and headline metric

Every provider response is normalized to five funding fields:

- Latest funding stage
- Latest funding date
- Latest round amount
- Total raised
- Funding-round count

The headline metric is **correct stage yield**: LLM-judged correct latest stages divided by all 300 Ground Truth-reviewed companies. The rubric handles documented funding-stage equivalents and exact date/amount evidence for non-Series disagreements. Missing or incorrect provider stages lower yield; blank Ground Truth is a pass-through case and Undisclosed Ground Truth accepts a blank vendor stage.

The other four fields contribute to the separate returned-data coverage metric; they are retained but not headline-scored in this release.

## Repository map

| Path | Contents |
|---|---|
| `data/funding/company-funding-inputs-v1.csv` | Exact frozen 300-domain input list and primary-source funding references |
| `data/latest-funding.json` | Publication snapshot: Ground Truth, 3,300 normalized provider outputs, LLM verdicts/reasons, and leaderboard |
| `data/funding/pricing-v1.json` | Dated public entry-tier cost assumptions used for the estimated USD cost display |
| `scripts/funding/run_funding_benchmark.py` | Credit-safe, resumable provider runner |
| `scripts/funding/smoke_test_funding_providers.py` | Small contract smoke test for the original endpoint adapters |
| `scripts/funding/run_structured_web_research.py` | Five-case Exa/Parallel structured-output contract pilot; raw outputs remain local |
| `scripts/funding/run_crustdata_funding_batch.py` | Credit-safe submit/poll runner for Crustdata's 300-company batch enrichment |
| `scripts/funding/score_funding_stage_dry_run.py` | Transparent latest-stage taxonomy and offline scoring report |
| `scripts/funding/judge_funding_stage.py` | Exact GPT-5.6 Terra v2 judge prompt and structured-output runner |
| `docs/company-funding/llm-judge-v2.md` | Public v2 matching policy and judge contract |
| `scripts/build_public_snapshot.py` | Builds the normalized publication snapshot from local runner checkpoints, excluding literal API response bodies |
| `scripts/recompute_funding_snapshot.py` | Recomputes every metric and leaderboard row from the committed snapshot without API calls |
| `scripts/verify_public_artifacts.py` | Zero-network integrity, cohort, and leaderboard checks |

See [DATA.md](DATA.md) for the schemas and [the methodology](docs/company-funding/methodology.md) for the complete public sourcing and evaluation contract.

## Verify without API calls

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=scripts .venv/bin/python scripts/verify_public_artifacts.py
```

The verifier checks the frozen 300-company cohort, all 3,300 provider cells, all 3,300 LLM verdicts/reasons, the 300-company denominator, and the published leaderboard. It makes no network calls.

## Re-run live APIs

Copy `.env.example` to `.env.local` and configure only the providers you intend to run. Live calls require `--confirm-paid`. Existing cells of every status are skipped unless a retry status is explicitly selected, so a restart cannot silently spend credits again.

```bash
PYTHONPATH=scripts .venv/bin/python scripts/funding/run_funding_benchmark.py \
  --only fiber --confirm-paid
```

For the new providers, use `run_structured_web_research.py exa` or `parallel`
for the five-case contract pilot, and `run_crustdata_funding_batch.py submit`
then `poll` for Crustdata. Crunchbase is deliberately not rerun by a script: it
is a self-serve-plan CSV export, recorded as such in the snapshot.

The committed snapshot contains the normalized benchmark contract for every provider answer, including status, latency, errors, LLM stage verdicts/reasons, and safe adapter audit metadata. Literal vendor HTTP response bodies stay in local, ignored runner checkpoints and are not redistributed here.

## Providers

- Apollo
- CompanyEnrich
- Crunchbase (exported dataset; no API-latency score)
- Crustdata
- Exa
- Explorium
- Fiber
- Ocean.io
- Parallel
- People Data Labs
- PredictLeads

No vendor sponsors or controls this benchmark.
