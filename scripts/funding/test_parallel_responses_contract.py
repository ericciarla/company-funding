"""Contract tests for the Parallel Responses funding arm (no API calls).

Only the medium-effort arm is measured. The high-effort arm was published on
2026-08-15 and withdrawn on 2026-08-17.

The point of running Parallel twice is to isolate the endpoint. If the two arms
ever stop sending the same instruction and the same output schema, the
comparison silently stops meaning anything, so that parity is asserted here
rather than left to review.
"""

from __future__ import annotations

import json
import os
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
    "latest_stage": "Series B", "latest_announced_on": "2026-01-15",
    "latest_amount": 45_000_000, "currency": "USD",
    "total_raised": 70_000_000, "funding_round_count": 3,
}


def responses_body(text: str | None = None, annotations: list[dict] | None = None) -> dict:
    content: dict = {"type": "output_text", "text": json.dumps(VALUE) if text is None else text}
    if annotations is not None:
        content["annotations"] = annotations
    return {"id": "resp-test", "output": [{"content": [content]}]}


class ParallelResponsesContractTest(unittest.TestCase):
    def test_request_shape_matches_the_documented_responses_contract(self) -> None:
        captured: list[dict] = []

        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            captured.append({"url": url, "headers": headers, "body": payload})
            return responses_body()

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            normalized, raw = runner.parallel_responses(CASE)

        self.assertEqual(normalized, VALUE)
        self.assertEqual(raw["response_id"], "resp-test")
        self.assertEqual(len(captured), 1)
        call = captured[0]
        self.assertEqual(call["url"], "https://api.parallel.ai/v1/responses")
        self.assertEqual(call["headers"]["Authorization"], "Bearer test")
        self.assertEqual(set(call["body"]), {"model", "input", "reasoning", "text"})
        self.assertEqual(call["body"]["model"], "parallel")
        self.assertEqual(call["body"]["reasoning"], {"effort": "medium"})
        self.assertEqual(call["body"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(call["body"]["text"]["format"]["schema"], runner.OUTPUT_SCHEMA)
        self.assertEqual(call["body"]["input"], runner.instruction(CASE))

    def test_both_parallel_arms_send_the_same_instruction_and_schema(self) -> None:
        """The endpoint must be the only difference between the two arms."""
        captured: list[dict] = []

        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            captured.append({"url": url, "body": payload})
            if url.endswith("/v1/responses"):
                return responses_body()
            if url.endswith("/v1/tasks/runs"):
                return {"run_id": "trun-test"}
            return {"status": "completed", "output": {"content": VALUE}}

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            responses_normalized, _ = runner.parallel_responses(CASE)
            tasks_normalized, _ = runner.parallel(CASE)

        self.assertEqual(responses_normalized, tasks_normalized)
        responses_body_sent = captured[0]["body"]
        tasks_body_sent = captured[1]["body"]
        self.assertEqual(
            responses_body_sent["text"]["format"]["schema"],
            tasks_body_sent["task_spec"]["output_schema"]["json_schema"],
        )
        self.assertEqual(responses_body_sent["input"], tasks_body_sent["input"]["instruction"])

    def test_reference_values_never_reach_the_provider(self) -> None:
        captured: list[dict] = []

        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            captured.append(payload)
            return responses_body()

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            runner.parallel_responses(CASE)

        sent = json.dumps(captured[0])
        for leaked in ("Series B", "2026-01-15", "45000000"):
            self.assertNotIn(leaked, sent)

    def test_citations_are_captured_into_raw_and_kept_out_of_normalized(self) -> None:
        annotations = [
            {"type": "url_citation", "url": "https://example.com/press", "title": "Press"},
            {"type": "url_citation", "url": "https://example.com/press", "title": "Duplicate"},
            {"type": "url_citation", "url": "https://investor.example/post", "title": "Investor"},
        ]

        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            return responses_body(annotations=annotations)

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            normalized, raw = runner.parallel_responses(CASE)

        self.assertEqual(raw["sources"], ["https://example.com/press", "https://investor.example/post"])
        self.assertEqual(raw["reasoning_effort"], "medium")
        self.assertNotIn("sources", normalized)
        self.assertEqual(set(normalized), set(runner.OUTPUT_SCHEMA["properties"]))

    def test_prose_from_a_schema_request_is_recorded_verbatim(self) -> None:
        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            return responses_body(text="Example Company raised a Series B.")

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            normalized, _ = runner.parallel_responses(CASE)

        self.assertEqual(normalized, {"unparsed_text": "Example Company raised a Series B."})

    def test_missing_output_text_is_an_error_not_an_empty_result(self) -> None:
        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            return {"id": "resp-test", "output": []}

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request), \
             self.assertRaises(ValueError):
            runner.parallel_responses(CASE)

    def test_provider_is_registered_for_the_cli(self) -> None:
        slug = "parallel-responses-medium"
        self.assertIn(slug, runner.PROVIDERS)
        self.assertEqual(runner.REQUIRED_ENV[slug], "PARALLEL_API_KEY")
        self.assertEqual(runner.DEFAULT_CONCURRENCY[slug], 8)
        self.assertEqual(runner.PROVIDERS[slug], runner.parallel_responses)

    def test_high_effort_arm_is_gone(self) -> None:
        """Withdrawn 2026-08-17. Re-registering it silently would republish it."""
        self.assertNotIn("parallel-responses", runner.PROVIDERS)
        self.assertEqual(runner.RESPONSES_REASONING_EFFORT, "medium")

    def test_effort_is_recorded_on_the_saved_cell(self) -> None:
        def fake_request(url: str, headers: dict, payload: dict | None = None) -> dict:
            return responses_body()

        with patch.dict(os.environ, {"PARALLEL_API_KEY": "test"}), \
             patch.object(runner, "request_json", fake_request):
            _, raw = runner.PROVIDERS["parallel-responses-medium"](CASE)

        self.assertEqual(raw["reasoning_effort"], "medium")


if __name__ == "__main__":
    unittest.main()
