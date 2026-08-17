"""Contract tests for the two Exa funding arms (no API calls).

The point of running Exa twice is to isolate the search type. If the arms ever
stop sending the same query and the same output schema, the comparison silently
stops meaning anything, so that parity is asserted here rather than left to
review.

Also pins the raw envelope shape: deep-reasoning cells already published on the
board store the bare Exa response, and changing that would break re-normalizing
them from disk.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from funding import run_structured_web_research as runner


CASE = {
    "candidate_id": "contract-case",
    "company_name": "Example Company",
    "company_domain": "example.com",
    # Reference columns ride along in the real CSV row. None of them may ever
    # reach a provider request.
    "ground_truth_stage": "Series B",
    "ground_truth_announced_on": "2026-01-15",
    "ground_truth_amount": "45000000",
}

VALUE = {
    "latest_stage": "Series B",
    "latest_announced_on": "2026-01-15",
    "latest_amount": 45_000_000,
    "currency": "USD",
    "total_raised": 60_000_000,
    "funding_round_count": 3,
}


class ExaSearchTypeParity(unittest.TestCase):
    def test_search_type_is_the_only_difference(self) -> None:
        deep = runner.exa_payload(CASE, "deep-reasoning")
        instant = runner.exa_payload(CASE, "instant")
        self.assertEqual(deep["type"], "deep-reasoning")
        self.assertEqual(instant["type"], "instant")
        del deep["type"], instant["type"]
        self.assertEqual(deep, instant, "Exa arms diverge beyond search type")

    def test_query_matches_the_shared_instruction(self) -> None:
        """Every provider on the board is asked the same thing."""
        for search_type in runner.EXA_SEARCH_TYPES:
            self.assertEqual(
                runner.exa_payload(CASE, search_type)["query"],
                runner.instruction(CASE),
            )

    def test_both_arms_send_the_shared_output_schema(self) -> None:
        for search_type in runner.EXA_SEARCH_TYPES:
            self.assertIs(
                runner.exa_payload(CASE, search_type)["output_schema"],
                runner.OUTPUT_SCHEMA,
            )

    def test_no_reference_data_reaches_the_request(self) -> None:
        blob = json.dumps(runner.exa_payload(CASE, "instant"))
        for leak in ("Series B", "2026-01-15", "45000000", "ground_truth"):
            self.assertNotIn(leak, blob)

    def test_both_arms_registered_for_the_cli(self) -> None:
        self.assertIn("exa", runner.PROVIDERS)
        self.assertIn("exa-instant", runner.PROVIDERS)
        self.assertEqual(runner.REQUIRED_ENV["exa-instant"], "EXA_API_KEY")

    def test_default_arm_is_unchanged(self) -> None:
        """The published `exa` row must keep meaning deep-reasoning."""
        self.assertEqual(runner.EXA_DEFAULT_SEARCH_TYPE, "deep-reasoning")


class ExaEnvelope(unittest.TestCase):
    def _run(self, search_type: str, response: dict):
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}), patch.object(
            runner, "request_json", return_value=response
        ):
            return runner.exa(CASE, search_type=search_type)

    def test_raw_stays_the_bare_response_plus_request_type(self) -> None:
        """Published deep-reasoning cells store the bare response; keep it."""
        response = {
            "output": {"content": VALUE},
            "costDollars": {"total": 0.015},
            "requestId": "abc123",
        }
        normalized, raw = self._run("instant", response)
        self.assertEqual(normalized, VALUE)
        # Every original field survives untouched.
        self.assertEqual(raw["costDollars"], {"total": 0.015})
        self.assertEqual(raw["requestId"], "abc123")
        self.assertEqual(raw["_request_type"], "instant")

    def test_missing_structured_output_is_an_error_not_an_empty_result(self) -> None:
        """A cheap search type that cannot honour the schema must not score 0."""
        with self.assertRaises(ValueError):
            self._run("instant", {"results": [], "costDollars": {"total": 0.001}})


class ExaAgentContract(unittest.TestCase):
    """The Agent API is a third Exa arm: an agent, not a search call."""

    def test_asks_the_same_question_with_the_same_schema(self) -> None:
        payload = runner.exa_agent_payload(CASE, "medium")
        self.assertEqual(payload["query"], runner.instruction(CASE))
        # Note the spelling: /agent/runs takes outputSchema, /search takes
        # output_schema. Sending the wrong one loses structured output silently.
        self.assertIs(payload["outputSchema"], runner.OUTPUT_SCHEMA)
        self.assertNotIn("output_schema", payload)

    def test_effort_is_pinned_and_never_auto(self) -> None:
        """"auto" meters up to $5 per run: ~$1,500 across a 300-domain cohort."""
        self.assertIn(
            runner.EXA_AGENT_EFFORT,
            {"minimal", "low", "medium", "high", "xhigh"},
        )
        self.assertEqual(
            runner.exa_agent_payload(CASE, runner.EXA_AGENT_EFFORT)["effort"],
            runner.EXA_AGENT_EFFORT,
        )

    def test_no_budget_is_sent(self) -> None:
        """The API 400s on a budget for a fixed effort, and it is redundant:
        pinning the effort already fixes the per-request price."""
        self.assertNotIn("budget", runner.exa_agent_payload(CASE, "medium"))

    def test_no_reference_data_reaches_the_request(self) -> None:
        blob = json.dumps(runner.exa_agent_payload(CASE, "medium"))
        for leak in ("Series B", "2026-01-15", "45000000", "ground_truth"):
            self.assertNotIn(leak, blob)

    def test_registered_under_the_shared_exa_key(self) -> None:
        self.assertIn("exa-agent", runner.PROVIDERS)
        self.assertEqual(runner.REQUIRED_ENV["exa-agent"], "EXA_API_KEY")

    def _run(self, *responses):
        calls = iter(responses)

        def fake(url, headers, payload=None, timeout=180):
            # Bearer here, x-api-key on /search. Getting this wrong 401s.
            self.assertTrue(headers["Authorization"].startswith("Bearer "))
            return next(calls)

        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}), patch.object(
            runner, "request_json", fake
        ), patch.object(runner.time, "sleep", lambda _s: None):
            return runner.exa_agent(CASE)

    def test_queued_run_is_polled_to_completion(self) -> None:
        normalized, raw = self._run(
            {"id": "agent_run_1", "status": "queued"},
            {"id": "agent_run_1", "status": "running"},
            {
                "id": "agent_run_1",
                "status": "completed",
                "output": {"structured": VALUE, "text": "…", "grounding": [{"x": 1}]},
                "costDollars": 0.1,
                "usage": {"agentComputeUnits": 1},
            },
        )
        self.assertEqual(normalized, VALUE)
        self.assertEqual(raw["run_id"], "agent_run_1")
        self.assertEqual(raw["cost_dollars"], 0.1)
        self.assertEqual(raw["usage"], {"agentComputeUnits": 1})
        # Grounding must not leak into the scored contract.
        self.assertNotIn("grounding", normalized)

    def test_failed_run_raises_rather_than_scoring_zero(self) -> None:
        with self.assertRaises(ValueError):
            self._run({"id": "r", "status": "failed", "error": "boom"})

    def test_prose_from_a_completed_run_is_recorded_verbatim(self) -> None:
        normalized, _ = self._run(
            {
                "id": "r",
                "status": "completed",
                "output": {"text": "It raised a Series B."},
            },
        )
        self.assertEqual(normalized, {"unparsed_text": "It raised a Series B."})


if __name__ == "__main__":
    unittest.main()
