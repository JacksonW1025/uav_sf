# Family A Fuzzer v0 V0-P qualification readiness amendment

Status: `READINESS_RESOLVED_PENDING_INDEPENDENT_REVIEW`

This amendment addresses the implementation and reproducible environment
readiness gaps recorded by the independent activation review at
`5db3934c58553e491b19fe8da106948fe8cd1d16`. It is limited to static readiness
validation for flight-software reliability, runtime consistency, route
conformance, lifecycle progression, bounded qualification, deterministic
scenario mapping, evidence collection, safety monitoring, cleanup
verification, and a reproducible environment.

The original `DECLINE_IMPLEMENTATION_NOT_READY` decision remains unchanged and
correct for its reviewed commit. This amendment is not an activation decision,
does not authorize runtime, and creates no formal attempt.

## Resolution boundary

The 11 original blocking clauses are resolved by new static contracts:

| Clauses | Static resolution |
|---|---|
| `G-01`, `G-10` | one V0-P runner with explicit `plan`, `preflight`, and guarded `execute`; only `V0_P_QUALIFICATION` and `QUALIFICATION` are admitted |
| `G-02` | six fixed runbook slots mapped to six accepted current Family A seeds |
| `G-05` | hashed per-slot scenario, adapter, collector, and Oracle bindings |
| `G-07` | compact-evidence template and completed-evidence validation with non-collapsing outcomes |
| `G-08` | cleanup audit covering terminal state, runner exit, collector closure, file flush, artifact closure, process residue, and ports |
| `H-01`, `H-02` | one safety entry using the frozen finite-value and physical boundaries |
| `H-07`, `H-08` | read-only preflight and post-attempt process-tree, stale-state, and UDP/TCP port checks |
| `J-03` | exact ROS Jazzy/Gazebo Harmonic container, dependency, workspace, Python, DDS, setup, and verification identities |

The clause-level record is
[blocker_resolution_matrix.tsv](../../experiments/fuzzer_v0/family_a/readiness_amendment/blocker_resolution_matrix.tsv).
No seed row, comparison budget, Oracle threshold, safety boundary, state
model, event grammar, mutation grammar, activation decision, or attempt ledger
is changed.

## Unique V0-P path

The only formal runner entry is
`scripts/fuzzer_v0/family_a/run_v0p_qualification.py`.

- No subcommand starts nothing and exits nonzero.
- `plan` parses the fixed six-slot map and emits only static JSON.
- `preflight` checks frozen identities, component hashes, environment identity,
  current authorization/accounting state, residual processes, port 8888, and
  repository cleanliness.
- `execute` first enforces phase, strategy, seed, slot, independent decision
  commit, and `AUTHORIZED_NOT_STARTED` ledger requirements.
- The current original DECLINE decision causes `execute` to refuse before any
  scenario or process entry can be called.

Official Sequence, Bounded Random Timing Comparator, State-Aware Mutation,
historical replay, real workload, Family B, direct actuator, unmapped seeds,
and a seventh attempt are rejected by the same entry. The runner does not read
or import the pre-M-FINAL executor and emits no Route Oracle 0.3 identity.

## Deterministic scenario mapping

The [scenario map](../../experiments/fuzzer_v0/family_a/readiness_amendment/qualification_scenario_map.tsv)
preserves the runbook order:

1. `P0_A_OFFBOARD_ADMISSION`
2. `P0_B_DYNAMIC_ADMISSION`
3. `P0_C_EXECUTOR_COMPLETION`
4. `P3_OFFBOARD_H1_S0`
5. `P2_DYNAMIC_SIGTERM`
6. `C1_PAIR_B`

Every row is checked against the frozen seed catalog for source campaign,
source artifact, mechanism, route pair, setpoint level, lifecycle sequence,
current runtime status, accepted status, and integrity. Maximum slot use is
one. The accepted target remains three and the formal maximum remains six.

## Evidence, safety, and cleanup

The [implementation manifest](../../experiments/fuzzer_v0/family_a/readiness_amendment/implementation_manifest.yaml)
contains 25 exact component identities and six orchestration bindings. Large
existing scenario, adapter, collector, and Oracle implementations are reused.
The new layer binds them to:

- Route Oracle 0.4;
- Freshness Oracle 0.1 where applicable;
- Successor Progression Oracle 0.1 where applicable;
- Authority Event Linearization Oracle 0.2 for `C1_PAIR_B`;
- Evidence Admissibility Gate 1.0;
- compact evidence generation and validation;
- the frozen Family A safety profile; and
- cleanup plus process/port audit.

Blank compact evidence contains no default PASS or ACCEPTED value. Completed
evidence rejects missing applicable Oracle results, invalid clock evidence,
incomplete critical windows, non-PASS safety, non-CLEAN cleanup, and non-CLEAN
process/port audits. `UNKNOWN`, `NOT_APPLICABLE`, and `EXPOSURE` retain their
frozen meanings.

The safety entry reads boundaries only from `safety_rules.yaml`. It checks
finite command, controller, and actuator observations; height; commanded and
observed horizontal and vertical speed; attitude; body rate; unexpected
ground contact; PX4 abort; clock stall; critical-window completeness; route
epoch; writer/controller lineage; Land/Disarm completion; and timeout. Missing
data is never treated as safe.

## Reproducible ROS Jazzy environment

The [environment lock](../../experiments/fuzzer_v0/family_a/readiness_amendment/environment_lock.yaml)
selects the repository's existing digest-locked container:

- ROS Jazzy;
- Gazebo Harmonic;
- Ubuntu base image by SHA-256 digest;
- aarch64;
- Python 3.12.3;
- exact PX4, `px4_msgs`, `px4-ros2-interface-lib`, and Micro XRCE-DDS Agent
  commits;
- the Family A setup and workspace scripts; and
- UDP/TCP campaign port 8888.

The host Humble installation is recorded but is not an admissible replacement
and is not selected. Static availability proves that the reproducible
environment contract is complete and parseable; it is not runtime evidence.

## Readiness Gate

The machine Gate is
[static_readiness_gate.json](../../experiments/fuzzer_v0/family_a/readiness_amendment/static_readiness_gate.json)
and validates against
[family_a_fuzzer_v0_readiness_gate.schema.json](../../data/schemas/family_a_fuzzer_v0_readiness_gate.schema.json).

Its status is `READINESS_RESOLVED_PENDING_INDEPENDENT_REVIEW`, while:

- `qualification_authorized = false`
- `runtime_authorized = false`
- `formal_attempts_authorized = false`
- `comparison_runtime_authorized = false`
- `formal_attempts = 0`
- `requires_independent_activation_rereview = true`

No PX4, Gazebo, ROS launch, DDS flight communication, flight scenario,
qualification attempt, or comparison arm was executed.

The next exact action is: perform a new independent static qualification
activation review.
