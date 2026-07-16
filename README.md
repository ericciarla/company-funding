# Company Funding Benchmark

Open data and reproducible runner code for the [OpenBenchmarks Company Funding Benchmark](https://openbenchmarks.com/company-funding).

The frozen release compares seven company-data APIs on the same 300 company domains. It is designed for GTM account prioritization and qualification: companies with known funding transitions are intentionally over-sampled so that the benchmark tests an actionable signal rather than mostly empty records.

## Evaluated fields and headline metric

Every provider response is normalized to five funding fields:

- Latest funding stage
- Latest funding date
- Latest round amount
- Total raised
- Funding-round count

The headline metric is **correct stage yield**: correct canonical latest stages divided by companies with a specific, source-verified latest-stage reference. Missing or incorrect provider stages lower yield. Missing or vague reference stages are excluded from its denominator.

The other four fields contribute to the separate returned-data coverage metric; they are retained but not headline-scored in this release.

## Repository map

| Path | Contents |
|---|---|
| `data/funding/company-funding-inputs-v1.csv` | Exact frozen 300-domain input list and primary-source funding references |
| `data/latest-funding.json` | Publication snapshot: reference records, 2,100 normalized provider outputs, deterministic judgments, and leaderboard |
| `data/funding/pricing-v1.json` | Dated public entry-tier cost assumptions used for the estimated USD cost display |
| `scripts/funding/run_funding_benchmark.py` | Credit-safe, resumable provider runner |
| `scripts/funding/smoke_test_funding_providers.py` | Small contract smoke test and seven provider endpoint adapters |
| `scripts/funding/score_funding_stage_dry_run.py` | Transparent latest-stage taxonomy and offline scoring report |
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

The verifier checks the frozen 300-company cohort, all 2,100 provider cells, the 268-company stage denominator, and the published leaderboard. It makes no network calls.

## Re-run live APIs

Copy `.env.example` to `.env.local` and configure only the providers you intend to run. Live calls require `--confirm-paid`. Existing cells of every status are skipped unless a retry status is explicitly selected, so a restart cannot silently spend credits again.

```bash
PYTHONPATH=scripts .venv/bin/python scripts/funding/run_funding_benchmark.py \
  --only fiber --confirm-paid
```

The committed snapshot contains the normalized benchmark contract for every provider answer, including status, latency, errors, stage verdicts, and adapter audit metadata. Literal vendor HTTP response bodies stay in local, ignored runner checkpoints and are not redistributed here.

## Providers

- Apollo
- CompanyEnrich
- Explorium
- Fiber
- Ocean.io
- People Data Labs
- PredictLeads

No vendor sponsors or controls this benchmark.
