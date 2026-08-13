"""Tests for same-trace Oracle ablation and per-transition replay."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from scripts.analysis.corpus import load_frozen_corpus
from scripts.analysis.oracle_ablation import (
    evaluate_full_suite_posthoc,
    evaluate_mode_only,
    evaluate_safuzz_adaptation,
    evaluate_terminal_only,
)
from tests.helpers import (
    chain,
    identity,
    passing_events,
    passing_raw_events,
    plan,
    raw_event,
)


class OracleAblationTests(unittest.TestCase):
    def test_simple_observation_layers_pass_without_route_identity(self) -> None:
        events = passing_events()
        experiment = plan()
        mode = evaluate_mode_only(events, experiment)
        terminal = evaluate_terminal_only(events, experiment)
        safuzz = evaluate_safuzz_adaptation(events, experiment)
        self.assertEqual(mode["status"], "PASS")
        self.assertEqual(terminal["status"], "PASS")
        self.assertEqual(safuzz["raw_verdict"], "Passing")
        forbidden = {
            "route_epoch",
            "producer_session",
            "registration_id",
            "activation_id",
            "command_subject_ns",
            "controller_id",
            "allocator_id",
            "writer_id",
            "lifecycle_owner",
            "executor_owner",
        }
        self.assertFalse(forbidden & set(safuzz["observation_fields"]))

    def test_missing_terminal_observation_is_unknown_not_pass(self) -> None:
        raw = [event for event in passing_raw_events() if event["kind"] != "terminal_state"]
        result = evaluate_terminal_only(chain(raw), plan())
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["raw_verdict"], "Unknown")

    def test_second_matching_transition_is_evaluated_independently(self) -> None:
        experiment = plan()
        experiment["transition"]["target_activation_count"] = [2, 2]
        raw = [
            event
            for event in passing_raw_events()
            if event["kind"] not in {"terminal_state", "collection_stopped"}
        ]
        source = identity("legacy_offboard", "source-two")
        target = identity("dynamic_external_mode", "target-two")
        successor = identity("internal_hold", "successor-two")
        raw.extend(
            [
                raw_event("activation", 190_000_000, **source),
                raw_event(
                    "actuator_write",
                    205_000_000,
                    command_subject_ns=190_000_000,
                    **source,
                ),
                raw_event(
                    "transition_requested",
                    210_000_000,
                    source_route="legacy_offboard",
                    target_route="dynamic_external_mode",
                ),
                raw_event("revocation", 216_000_000, **source),
                raw_event("activation", 220_000_000, **target),
                raw_event("command_consumed", 222_000_000, command_subject_ns=0, **target),
                raw_event("controller_output", 224_000_000, command_subject_ns=0, **target),
                raw_event("allocator_output", 226_000_000, command_subject_ns=0, **target),
                raw_event("actuator_write", 228_000_000, command_subject_ns=0, **target),
                raw_event("completion", 250_000_000, route="dynamic_external_mode"),
                raw_event("revocation", 251_000_000, **target),
                raw_event("activation", 260_000_000, **successor),
                raw_event(
                    "command_consumed",
                    262_000_000,
                    command_subject_ns=255_000_000,
                    **successor,
                ),
                raw_event(
                    "controller_output",
                    264_000_000,
                    command_subject_ns=255_000_000,
                    **successor,
                ),
                raw_event(
                    "allocator_output",
                    266_000_000,
                    command_subject_ns=255_000_000,
                    **successor,
                ),
                raw_event(
                    "actuator_write",
                    268_000_000,
                    command_subject_ns=255_000_000,
                    **successor,
                ),
                raw_event(
                    "terminal_state",
                    300_000_000,
                    route="internal_hold",
                    landed=True,
                    disarmed=True,
                ),
                raw_event("collection_stopped", 600_000_000),
            ]
        )
        result = evaluate_full_suite_posthoc(chain(raw), experiment)
        self.assertEqual(len(result["transition_instances"]), 2)
        self.assertEqual(result["transition_instances"][0]["status"], "PASS")
        self.assertEqual(result["transition_instances"][1]["status"], "VIOLATION")
        self.assertEqual(result["status"], "VIOLATION")

    def test_frozen_corpus_is_read_only_and_has_all_admissible_traces(self) -> None:
        if not Path("runs/motivation-thor-v1").is_dir():
            self.skipTest("retained runtime traces are unavailable")
        corpus = load_frozen_corpus(Path("."))
        self.assertEqual(len(corpus), 151)
        self.assertEqual(
            {record.study_id for record in corpus},
            {"motivation-thor-v1", "motivation-thor-remediation-v1"},
        )
        self.assertTrue(all(record.outcome == "ACCEPTED" for record in corpus))


if __name__ == "__main__":
    unittest.main()
