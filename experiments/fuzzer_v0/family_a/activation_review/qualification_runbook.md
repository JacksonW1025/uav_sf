# Family A Fuzzer v0 V0-P qualification runbook

Status: `NOT_AUTHORIZED`

This runbook defines a future controlled SITL qualification sequence. It does
not authorize or execute the sequence. The activation review declined
qualification because the required V0-P-only runner, executable scenario
mapping, evidence integration, cleanup audit, and locked ROS Jazzy environment
are not ready. Every command marked `REQUIRED_FUTURE_ENTRY` names an interface
contract that does not currently exist and must not be invoked or substituted
with the pre-M-FINAL prototype.

## Exact identity

The future qualification must start from the reviewed preregistration commit
`426f4c7316e973c6a4dab84a202fdb75ea65b7c1` or an explicitly reviewed
descendant that leaves every frozen bundle hash unchanged.

| Dependency | Required identity |
|---|---|
| PX4 | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| `px4_msgs` | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| `px4-ros2-interface-lib` | `c3e410f035806e8c56246708432ded09c976434b` |
| Micro XRCE-DDS Agent | `73622810d984349b80bbac0ef55fc0b694d62222` |
| ROS | Jazzy |
| Gazebo | Harmonic |
| vehicle/world | `gz_x500` / `default` |
| Route Oracle | `0.4` |
| Freshness Oracle | `0.1` |
| Successor Progression Oracle | `0.1` |
| Authority Event Linearization Oracle | `0.2` |
| Evidence Admissibility Gate | `1.0` |

The [review source lock](review_source_lock.yaml) contains the complete starting
identity and frozen hashes.

## Exact environment setup

The required environment is repository-relative except for the standard ROS
installation prefix:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export QUALIFICATION_RAW_ROOT=runs/fuzzer_v0/family_a/qualification
export QUALIFICATION_COMPACT_ROOT=data/processed/fuzzer_v0/family_a/qualification
```

The review host did not contain `/opt/ros/jazzy/setup.bash`. The setup block is
therefore a future requirement, not an instruction authorized by this review.
The legacy Humble P5 environment is not an admissible replacement.

## Fixed qualification seed schedule

V0-P uses canonical parameterization only. It has no Official Sequence,
Bounded Random Timing, or State-Aware strategy identity, performs no mutation,
and does not update comparison coverage or metrics.

| Formal slot | Attempt ID | Seed ID | Simulator seed | Qualification obligation |
|---|---|---|---:|---|
| 1 | `V0P-A1` | `P0_A_OFFBOARD_ADMISSION` | 410101 | Offboard route installation and cleanup |
| 2 | `V0P-A2` | `P0_B_DYNAMIC_ADMISSION` | 410102 | Dynamic External Mode registration, activation, route installation, and cleanup |
| 3 | `V0P-A3` | `P0_C_EXECUTOR_COMPLETION` | 410103 | lifecycle owner, successor progression, route installation, and cleanup |
| 4 | `V0P-A4` | `P3_OFFBOARD_H1_S0` | 410104 | retained-route command freshness, bounded window, and cleanup |
| 5 | `V0P-A5` | `P2_DYNAMIC_SIGTERM` | 410105 | owned-process loss, fallback, command lineage, and cleanup |
| 6 | `V0P-A6` | `C1_PAIR_B` | 410106 | bounded authority-event linearization, successor progression, and cleanup |

Only the next slot is eligible for registration. The phase stops immediately
at three `ACCEPTED` attempts or after slot six is classified. Slots four
through six are predeclared qualification slots, not automatic replacements
for rejected attempts. No unused slot transfers to a comparison arm.

## Preflight static check

The future task must complete these read-only checks before it registers an
attempt:

```bash
git status --short --branch
python3 scripts/setup/verify_dependency_lock.py --json
python3 scripts/validation/check_family_a_fuzzer_v0_preregistration.py
python3 scripts/validation/check_family_a_fuzzer_v0_activation_review.py
pgrep -af 'px4|gz sim|MicroXRCEAgent|ros2|family_a_qualification' || true
ss -H -lun 'sport = :8888'
```

The process audit must distinguish unrelated host text from executable process
identity. Port `8888` must have no listener. All frozen hashes, dependency
commits, the pushed activation identity, the next ledger slot, and the clean
worktree must pass before registration.

## Required future runner interface

The following interface is the required command shape. The referenced runner
does not exist at this review commit:

```bash
# REQUIRED_FUTURE_ENTRY — NOT EXECUTABLE AT THIS REVIEW COMMIT
python3 scripts/fuzzer/family_a_qualification_runner.py \
  --phase V0-P \
  --attempt-id "${ATTEMPT_ID}" \
  --seed-id "${SEED_ID}" \
  --simulation-seed "${SIMULATION_SEED}" \
  --raw-root "${QUALIFICATION_RAW_ROOT}" \
  --compact-root "${QUALIFICATION_COMPACT_ROOT}"
```

The runner must reject every strategy argument, comparison-arm identifier,
historical replay row, non-`ACCEPTED_RUNTIME_SEED` row, noncanonical mutation,
and attempt ID other than the ledger's next slot. It must bind the exact
adapter, scenario, collector, Oracle, safety, and cleanup entries before
launch.

## Formal attempt registration

Registration must occur after static preflight and before any simulator,
transport, adapter, recorder, monitor, or flight process starts:

```bash
# REQUIRED_FUTURE_ENTRY — NOT EXECUTABLE AT THIS REVIEW COMMIT
python3 scripts/fuzzer/family_a_qualification_ledger.py register \
  --ledger experiments/fuzzer_v0/family_a/activation_review/qualification_attempt_ledger.yaml \
  --attempt-id "${ATTEMPT_ID}" \
  --seed-id "${SEED_ID}" \
  --simulation-seed "${SIMULATION_SEED}"
```

The append-only record must include repository and dependency identity,
activation decision identity, seed row hash, runner configuration hash, raw
and compact roots, and a `REGISTERED_NOT_STARTED` state. A registered attempt
cannot be deleted, renumbered, overwritten, or removed from the six-attempt
maximum.

## Recorder and Oracle templates

The future runner must invoke the locked components directly and preserve their
arguments in compact evidence. Representative command shapes are:

```bash
python3 scripts/tracing/route_trace_collector.py \
  --ulog "${RAW_ATTEMPT_ROOT}/flight.ulg" \
  --output "${COMPACT_ATTEMPT_ROOT}/route_trace.jsonl" \
  --run-id "${ATTEMPT_ID}"

python3 scripts/tracing/clock_bridge_collector.py \
  --samples "${RAW_ATTEMPT_ROOT}/monitor_events.jsonl" \
  --output "${COMPACT_ATTEMPT_ROOT}/clock_bridge.json"

python3 scripts/oracles/route_oracle_v0.py \
  --trace "${COMPACT_ATTEMPT_ROOT}/route_trace.jsonl" \
  --clock-bridge "${COMPACT_ATTEMPT_ROOT}/clock_bridge.json" \
  --source-artifact-complete \
  --output "${COMPACT_ATTEMPT_ROOT}/route_oracle.json"
```

Freshness, Successor, or Authority Event Linearization invocation is mandatory
when the frozen seed row marks that Oracle applicable. An applicable Oracle
that is missing or `UNKNOWN` prevents `ACCEPTED` classification.

## Safety monitor and cleanup

Before formal launch, the future V0-P safety monitor must pass a static
configuration check covering:

- non-finite command, controller, allocator, and actuator observations;
- target height and maximum altitude loss;
- commanded and observed horizontal and vertical speed;
- attitude and body-rate bounds;
- unexpected ground contact;
- PX4 abort, simulator clock stall, loss of simulator control, and timeout;
- clock-bridge and route critical-window completeness; and
- exact owned process and campaign-port identity.

Cleanup must stop mutated publication or resume an owned paused process as
required, request internal Hold if needed, request Land through the public
interface, observe land detection, request or observe Disarm, terminate only
owned experiment processes, and then run a separate residual-process and port
audit. Cleanup evidence is not part of the formal target window.

## Artifact and classification contract

Raw artifacts for an attempt belong only at:

```text
runs/fuzzer_v0/family_a/qualification/<attempt-id>/raw/
```

Compact evidence belongs at:

```text
data/processed/fuzzer_v0/family_a/qualification/<attempt-id>/
```

Every registered attempt requires SHA-256 identities for the raw manifest and
each compact artifact, a cleanup audit, and exactly one classification from:

- `ACCEPTED`
- `OBSERVABILITY_REJECTED`
- `MEASUREMENT_INSUFFICIENT`
- `ENVIRONMENT_FAILURE`
- `CAMPAIGN_CONFIGURATION_FAILURE`
- `FORMAL_SAFETY_STOP`
- `NOT_APPLICABLE`

Oracle `PASS`, `EXPOSURE`, `VIOLATION`, `UNKNOWN`, and `NOT_APPLICABLE` remain
separate from attempt classification. No qualification result enters strategy
superiority, the 36-attempt comparison budget, or a state-aware search-gain
claim.

## Post-phase adjudication

At three accepted attempts, V0-P closes as qualification-complete. At six
formal attempts with fewer than three accepted, it closes
`MEASUREMENT_INSUFFICIENT`. Any formal safety stop requires review, three
consecutive environment or configuration failures pause new registration, and
an identity mismatch revokes the execution path.

The next decision after a successful qualification must be separate. It may
review whether any comparison arm is ready, but it must not infer Official,
Bounded Random Timing, State-Aware, historical runtime, real-workload, Family
B, direct-actuator, HITL, or real-flight authorization from V0-P.
