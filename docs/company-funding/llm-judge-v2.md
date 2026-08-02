# Latest-stage LLM judge — v2

The 2026-08-01 snapshot evaluates every latest-stage provider response with `gpt-5.6-terra` at medium reasoning effort. The exact executable prompt and structured response schema are in [`scripts/funding/judge_funding_stage.py`](../../scripts/funding/judge_funding_stage.py).

The public snapshot records the model decision, decision basis, and concise reason for all 3,300 provider cells. The judge receives only the Ground Truth stage, date, and amount alongside the vendor's normalized stage, date, and amount; it does not browse or use company knowledge.

## Matching policy

- Series A–H require the same letter. Same-letter suffixes such as B1, B2, B3, B+, and `series_b_plus` match Series B.
- Seed, Seed Bridge, and Pre-Series A are equivalent. Seed and Pre-Seed are explicitly distinct.
- PE, PE Growth, Growth Investment/Equity, and strategic/corporate-investment variants are equivalent.
- Equity Crowdfunding, Grant, and Non-Equity Assistance are equivalent.
- Early Stage accepts Seed or Pre-Seed. Undisclosed accepts Undisclosed or a blank vendor stage. Blank Ground Truth passes every vendor answer.
- For other non-Series disagreements, an exactly matching date or amount can establish correctness.
