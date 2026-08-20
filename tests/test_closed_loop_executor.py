"""Tests for the in-flight loop that observes, filters, applies and re-selects."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest

from scripts.corpus.core_actions import core_action
from scripts.runtime.closed_loop_executor import (
    ClosedLoopError,
    TailReader,
    decision_is_due,
    request_path,
    run,
)
from scripts.runtime.closed_loop_policy import (
    STOP,
    create_policy,
    replay_decision_log,
)
from scripts.state.online_state import OnlineProjection


CLASS_ID = "process_exit_reclaim"
BOUNDS = {
    "terminate_owning_producer": [3_500_000_000, 6_500_000_000],
    "restart_producer_after_loss": [500_000_000, 2_500_000_000],
}
# Sidecar arrival times are placed in the past so the scheduled moment of every
# action has already come and the loop does not wait out a real ten seconds.
PAST_NS = 30_000_000_000


def policy(strategy: str = "official_sequence", seed: int | None = None):
    return create_policy(
        strategy=strategy,
        seed=seed,
        mechanism="legacy_offboard",
        class_id=CLASS_ID,
        timing_bounds_ns=BOUNDS,
        covered_units=set(),
    )


def record(kind: str, offset_ns: int, **payload):
    return {
        "kind": kind,
        "received_monotonic_ns": time.monotonic_ns() - PAST_NS + offset_ns,
        **payload,
    }


def append(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for value in records:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()


def route_active_records() -> list[dict]:
    """Takeoff, activation and motion: the tested route holds authority."""

    return [
        record("vehicle_land_detected", 0, landed=True),
        record("takeoff_requested", 1_000_000),
        record("vehicle_land_detected", 2_000_000, landed=False),
        record("vehicle_status", 3_000_000, nav_state=17),
        record("offboard_requested", 4_000_000),
        record("offboard_observed_active", 5_000_000, cycle=0),
        record("vehicle_status", 6_000_000, nav_state=14),
        record("motion_phase_entered", 7_000_000, along_track_progress_m=0.8),
    ]


def producer_lost_records() -> list[dict]:
    """The producer is gone and a safe route took over unasked."""

    return [
        record("fault_detected", 20_000_000, route="legacy_offboard", reason="source_process_exit"),
        record("vehicle_status", 21_000_000, nav_state=5),
    ]


class TailReaderTests(unittest.TestCase):
    def test_only_new_records_are_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s.jsonl"
            append(path, [record("completion", 0)])
            reader = TailReader(path)
            self.assertEqual(len(reader.read()), 1)
            self.assertEqual(reader.read(), [])
            append(path, [record("completion", 1)])
            self.assertEqual(len(reader.read()), 1)

    def test_a_missing_sidecar_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(TailReader(Path(directory) / "absent.jsonl").read(), [])

    def test_a_partial_line_is_held_until_it_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s.jsonl"
            path.write_text('{"kind": "completion", "received_mon', encoding="utf-8")
            reader = TailReader(path)
            self.assertEqual(reader.read(), [])
            with path.open("a", encoding="utf-8") as handle:
                handle.write('otonic_ns": 5}\n')
            self.assertEqual(len(reader.read()), 1)

    def test_a_truncated_sidecar_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s.jsonl"
            append(path, [record("completion", 0), record("completion", 1)])
            reader = TailReader(path)
            reader.read()
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ClosedLoopError):
                reader.read()

    def test_a_corrupt_complete_line_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s.jsonl"
            path.write_text("{not json}\n", encoding="utf-8")
            with self.assertRaises(ClosedLoopError):
                TailReader(path).read()


class DecisionPointTests(unittest.TestCase):
    def _projection(self, records):
        projection = OnlineProjection("legacy_offboard")
        projection.extend(sorted(records, key=lambda v: v["received_monotonic_ns"]))
        return projection

    def test_nothing_is_due_before_the_route_is_active(self):
        projection = self._projection([record("takeoff_requested", 0)])
        due, anchor = decision_is_due(projection, policy(), [])
        self.assertFalse(due)
        self.assertIsNone(anchor)

    def test_the_gate_alone_does_not_open_a_step(self):
        # External authority without a fault satisfies the termination's gate,
        # but the action also declares that motion has been entered, because it
        # is aimed at the straight translation.
        without_motion = [
            value
            for value in route_active_records()
            if value["kind"] != "motion_phase_entered"
        ]
        projection = self._projection(without_motion)
        gate = core_action("terminate_owning_producer").online_gate
        self.assertTrue(gate(projection.state))
        self.assertEqual(decision_is_due(projection, policy(), []), (False, None))

    def test_the_first_step_opens_on_the_termination_anchor(self):
        projection = self._projection(route_active_records())
        due, anchor = decision_is_due(projection, policy(), [])
        self.assertTrue(due)
        self.assertEqual(anchor, "route_active")

    def test_the_second_step_waits_for_the_fallback(self):
        projection = self._projection(route_active_records())
        applied = ["terminate_owning_producer"]
        self.assertEqual(decision_is_due(projection, policy(), applied), (False, None))
        projection.extend(
            sorted(producer_lost_records(), key=lambda v: v["received_monotonic_ns"])
        )
        due, anchor = decision_is_due(projection, policy(), applied)
        self.assertTrue(due)
        self.assertEqual(anchor, "fallback_installed")

    def test_a_terminal_episode_still_reaches_a_decision(self):
        # The policy gets to record that it stops, rather than the loop ending
        # silently and looking like a timeout.
        projection = self._projection(
            route_active_records() + [record("vehicle_land_detected", 30_000_000, landed=True)]
        )
        due, anchor = decision_is_due(projection, policy(), ["terminate_owning_producer"])
        self.assertTrue(due)
        self.assertIsNone(anchor)

    def test_a_terminal_episode_that_applied_nothing_is_not_due(self):
        projection = self._projection(
            [record("vehicle_land_detected", 0, landed=False), record("cleanup_completed", 1)]
        )
        self.assertEqual(decision_is_due(projection, policy(), []), (False, None))


class LoopTests(unittest.TestCase):
    def _arguments(self, directory: Path, value: dict, timeout_s: float = 30.0):
        (directory / "policy.json").write_text(json.dumps(value), encoding="utf-8")
        return types.SimpleNamespace(
            run_id="closed-loop-test",
            policy=directory / "policy.json",
            lifecycle=directory / "workload.lifecycle.jsonl",
            runner_lifecycle=directory / "runner.lifecycle.jsonl",
            telemetry=directory / "telemetry.sidecar.jsonl",
            request_dir=directory / "requests",
            decisions=directory / "decisions.json",
            output=directory / "closed-loop.lifecycle.jsonl",
            episode_timeout_s=timeout_s,
        )

    def _fly(self, value: dict, *, deliver_fallback: bool = True):
        """Run the loop while the sidecars are appended in stages around it."""

        directory = Path(tempfile.mkdtemp())
        args = self._arguments(directory, value)
        append(args.lifecycle, route_active_records())

        stop = threading.Event()

        def second_stage() -> None:
            # The fallback only becomes observable after the termination has
            # been requested, which is what makes the second decision depend on
            # the outcome of the first.
            target = request_path(args.request_dir, "terminate_owning_producer")
            while not stop.is_set():
                if target.is_file():
                    if deliver_fallback:
                        append(args.lifecycle, producer_lost_records())
                    else:
                        append(
                            args.lifecycle,
                            [record("vehicle_land_detected", 40_000_000, landed=True)],
                        )
                    return
                time.sleep(0.01)

        worker = threading.Thread(target=second_stage, daemon=True)
        worker.start()
        try:
            decisions = run(args)
        finally:
            stop.set()
            worker.join(timeout=2)
        return args, decisions

    def test_an_episode_carries_a_two_step_sequence(self):
        value = policy()
        args, decisions = self._fly(value)
        self.assertEqual(
            [step["selected_unit"] for step in decisions["steps"]],
            ["terminate_owning_producer:boundary", "restart_producer_after_loss:boundary"],
        )
        # Each action is requested on its own path, because each is consumed by
        # a different node.
        self.assertTrue(request_path(args.request_dir, "terminate_owning_producer").is_file())
        self.assertTrue(request_path(args.request_dir, "restart_producer_after_loss").is_file())

    def test_the_second_decision_used_the_state_the_first_produced(self):
        _, decisions = self._fly(policy())
        first, second = decisions["steps"]
        self.assertFalse(first["observed_state"]["fallback_installed"])
        self.assertTrue(second["observed_state"]["fallback_installed"])
        self.assertEqual(second["opened_by_marker"], "fallback_installed")
        self.assertEqual(second["applied_before"], ["terminate_owning_producer"])

    def test_each_action_is_measured_from_its_own_anchor(self):
        _, decisions = self._fly(policy())
        first, second = decisions["steps"]
        self.assertEqual(first["timing_anchor"], "route_active")
        self.assertEqual(second["timing_anchor"], "fallback_installed")
        self.assertNotEqual(first["anchor_observed_ns"], second["anchor_observed_ns"])

    def test_the_recorded_episode_replays_against_its_policy(self):
        # The whole contract: the flight chose, and the choice can be
        # re-derived from what it recorded.
        for strategy, seed in (
            ("official_sequence", None),
            ("bounded_random_timing", 21),
            ("state_aware", 21),
        ):
            value = policy(strategy, seed)
            _, decisions = self._fly(value)
            summary = replay_decision_log(value, decisions)
            self.assertEqual(summary["steps_replayed"], len(decisions["steps"]))

    def test_an_episode_that_never_reaches_the_second_anchor_stops_by_choice(self):
        _, decisions = self._fly(policy(), deliver_fallback=False)
        self.assertEqual(decisions["steps"][-1]["action"], STOP)
        summary = replay_decision_log(policy(), decisions)
        self.assertTrue(summary["stopped_by_choice"])
        self.assertEqual(summary["applied_actions"], ["terminate_owning_producer"])

    def test_a_loop_that_reaches_no_decision_point_refuses(self):
        # Running out of time is a refusal, never a recorded choice to stop.
        directory = Path(tempfile.mkdtemp())
        args = self._arguments(directory, policy(), timeout_s=0.4)
        append(args.lifecycle, [record("takeoff_requested", 0)])
        with self.assertRaises(ClosedLoopError):
            run(args)
        self.assertFalse(args.decisions.exists())

    def test_the_lifecycle_records_every_decision_and_application(self):
        args, decisions = self._fly(policy())
        kinds = [
            json.loads(line)["kind"]
            for line in args.output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(
            kinds,
            [
                "closed_loop_started",
                "closed_loop_decision",
                "closed_loop_applied",
                "closed_loop_decision",
                "closed_loop_applied",
                "closed_loop_completed",
            ],
        )

    def test_the_loop_refuses_to_overwrite_its_own_output(self):
        directory = Path(tempfile.mkdtemp())
        args = self._arguments(directory, policy())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")
        with self.assertRaises(ClosedLoopError):
            run(args)


if __name__ == "__main__":
    unittest.main()
