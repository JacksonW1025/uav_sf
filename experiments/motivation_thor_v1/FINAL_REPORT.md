# Thor Family A Motivation Study final report

## Decision

The preregistered study is `MEASUREMENT_INSUFFICIENT`. All 180 launches were
registered before execution and closed. Nineteen of 21 cells reached their
accepted-evidence targets; two timing/re-entry cells reached their launch caps
with no accepted evidence. The result must not be reported as a completely
successful study.

The 19 complete cells nevertheless provide admissible evidence for the
bounded AGX Thor SITL scope and identify independent Route, Freshness, and
Successor findings. A separately preregistered remediation is required before
entering later state-aware exploration.

## Frozen environment

- host: NVIDIA Jetson AGX Thor Developer Kit, aarch64;
- L4T: R38.2.1; host Ubuntu 24.04.3 LTS; kernel 6.8.12-tegra;
- explicit experiment runtime: `runc`, network namespace disabled;
- container: Ubuntu 24.04.4 LTS, Python 3.12.3, ROS 2 Jazzy,
  `rmw_fastrtps_cpp`, Gazebo Sim 8.11.0 (Harmonic);
- runtime source revision: `35971b4b4e9d03a738d0b28a1335ed8e4f2960b0`;
- image ID: `sha256:8c17f8f82d0e31d6ecac260ac84ec3b1ea3eedb67d887f27b9158c9331b24ef8`;
- PX4 SITL binary: `sha256:168c9a3d2e05d07a54d01f420d7a47dc58977eec0ece544c8c454e4f0c6bf619`;
- formal concurrency: four, with fixed and rotating CPU allocations.

CUDA 13.0 is present on the Thor host but is not exposed to or required by
the formal container. TensorRT and PyTorch are not study dependencies.

## Accounting and evidence

The append-only ledger contains 540 hash-chained events for 180 launches:

| Outcome | Count |
| --- | ---: |
| `ACCEPTED` | 131 |
| `OBSERVABILITY_REJECTED` | 20 |
| `TIMEOUT` | 28 |
| `ENVIRONMENT_FAILURE` | 1 |

There were no campaign-configuration failures and no formal safety stops.
Every retained ULog passed file, dropout, and RouteObservability sequence-gap
checks; none of the 180 ULogs contained a recorded sequence gap, dropout, or
file-corruption indication. All 131 accepted traces were admitted by the
Evidence Gate. Their clock uncertainty had median 1.956 ms and maximum
16.096 ms under the frozen 20 ms bound. Their central Gazebo real-time factor
had median 0.998732 and minimum 0.972699. Performance values are reported
separately from correctness decisions.

The compact results contain 75 overall Oracle passes and 56 overall Oracle
violations among accepted traces. `ACCEPTED` denotes admissible evidence, not
an Oracle pass.

## Cell closure

All nine deterministic cells reached 5 accepted traces. All seven fault cells
reached 8 accepted traces. Executor near, executor after, and Offboard
re-entry through Hold each reached 10 accepted traces.

Two cells exhausted 20 launches with zero accepted traces:

1. `timing-executor-before`: all 20 traces were rejected because the adjacent
   Land request legitimately preempted target completion, while the frozen
   plan incorrectly required a completion event. Runtime closure, ULog
   integrity, clock mapping, and Gazebo throughput did not justify treating
   the missing event as evidence.
2. `timing-offboard-reentry-rtl`: all 20 launches timed out before the first
   Offboard activation. The fixture required RTL as the initial source but did
   not establish that public precondition. This is an unreachable fixture
   setup, not evidence about repeated Offboard entry through RTL.

The single environment failure occurred after an expected Offboard
process-exit fallback had begun: the runner read a final, concurrently written
JSONL fragment and failed closed on the incomplete record. It consumed the
cell cap as required and was not interpreted as a SUT result.

## Findings within accepted evidence

Mode state and terminal landed/disarmed outcome were not sufficient to prove a
complete handoff:

- all five normal attitude-Offboard traces reached acceptable runtime closure,
  yet all five had Route violations: four missed complete installation within
  300 ms and one violated continuity;
- normal Dynamic Land and Hold each contained one admissible trace with a
  Freshness violation, and the Land trace also violated continuity;
- setpoint-stall and producer-exit cells retained safe terminal behavior while
  Freshness independently reported stale command consumption.

The Oracles contributed distinct information among the 131 accepted traces:

- Route Conformance: 14 violation clauses, including incomplete attitude-route
  installation and continuity failures;
- Freshness and Lineage: 40 violation clauses, including trajectory,
  attitude, body-rate, and process-exit stale-command cases;
- Successor Progression: 8 violation clauses, all from four executor-after
  traces whose adjacent request timing/order left the frozen bucket even
  though the Land successor was completely installed;
- Registration/Activation: 16 positive rejection-contract checks, with no
  accepted-trace violation of those rejection contracts.

Executor-near produced 10 admissible traces; three had independent Freshness
violations while adjacent timing and successor progression passed. Executor-
after produced 10 admissible traces; four left the timing/order bucket, while
the successor installation still passed. These observations justify retaining
route, freshness, and successor contracts as separate analyses.

## Scope and next decision

Claims are limited to PX4 SITL, `gz_x500`, headless Gazebo Harmonic, the exact
container and source identities above, and the tested public transition
sequences. They do not cover hardware-in-the-loop, real flight, search
algorithm comparison, or complete route-pair coverage.

Later state-aware exploration is not yet authorized. The next step is a new,
separate preregistration that fixes the JSONL snapshot reader and evaluates
only the two invalid primary cells with legal public preconditions. The
primary ledger, caps, outcomes, and conclusions remain unchanged.
