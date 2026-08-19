# Method

This file separates the target paper method from the implementation that is
available today. See [NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md) for rationale
and [CURRENT_STATUS.md](CURRENT_STATUS.md) for completed evidence.

## Target method

The target is evidence-gated, route-state-guided generation for PX4 authority
handoffs. It combines:

1. grey-box observation and semantic-state extraction;
2. admissibility and cross-layer contract Oracles;
3. a reachable action grammar with lifecycle preconditions;
4. closed-loop action-sequence and timing selection;
5. semantic-transition and contract-boundary feedback; and
6. replay, minimization, clustering, attribution, and full-stack validation.

The Oracle and generator are mutually enabling. The Oracle projects raw
execution into a state that generation can consume; the generator explores
conditions under which the Oracle obligations become informative. The paper's
headline is the generation method, but its feedback is not meaningful without
the route model and evidence discipline.

## Current implementation boundary

The executable prototype is narrower. It waits for `route_active` and
`motion_entered`, selects one owned action at a bounded time, and carries
timing-boundary coverage between launches in the same mechanism-strategy cell.

Qualified live actions are:

- `owned_setpoint_stall_v1`, with one completed 18-launch formal comparison;
- `owned_process_exit_fallback_v1`, with passing non-formal qualification and
  a preregistered candidate matrix containing zero formal launches.

The prototype does not yet implement the complete route, lifecycle, health,
registration, completion, successor, fallback, mission-context, and action-
history state. It is feasibility evidence, not the final method.

## Semantic state extraction

Adapters normalize PX4, ROS, lifecycle, workload, safety, and physical
observations into the event schema. Authority-bearing events carry the ten
stable Runtime Route Instance fields. Command-consumption and downstream-
effect events also carry `command_subject_ns`.

The state extractor derives the model in [ROUTE_MODEL.md](ROUTE_MODEL.md):

- route identity and epoch;
- owner and downstream lineage;
- lifecycle and replacement phase;
- registration, activation, health, and freshness;
- completion, successor, and fallback progress;
- coarse motion or mission context; and
- bounded action history.

The primary observation contract is grey-box. A reduced-observation replay
must quantify whether method behavior or finding classification depends on
custom instrumentation unavailable through ordinary PX4 interfaces.

The extractor is implemented in
[scripts/state/semantic_state.py](../scripts/state/semantic_state.py) against
the tracked contract in
[data/schemas/semantic_state.schema.json](../data/schemas/semantic_state.schema.json).
It folds one closed trace in hash-chain order into a state trajectory, uses no
declared-mode field, and represents unobserved evidence as an explicit unknown
rather than an inferred value. Motion context is an optional input from an
independent physical source; without samples every state reports `unobserved`.
The feedback unit `(semantic state, action, timing bucket) -> next semantic
state` is derived by the same fold. Extraction is offline today: the live
generator still consumes the narrower prototype state described above.

## Reachable action grammar

Actions are selected by lifecycle phase and mechanism provenance, not by
backend convenience. The core candidate space covers:

- register, activate, release, complete, replace, and re-enter;
- internal Hold, RTL, Land, Recovery, manual/GCS, and failsafe requests;
- producer exit or restart;
- callback or setpoint stall;
- communication delay or reconnect;
- health loss and capacity rejection; and
- adjacent or concurrent authority requests.

Every action has explicit preconditions, ownership, observable request and
effect markers, cleanup semantics, and safety limits. Unsupported action/state
combinations fail closed. Real mission traces, public interfaces, source
transitions, issue histories, and reproducible natural events provide
provenance and parameter ranges.

The final corpus is not frozen merely by this list. Each included action must
have a stated lifecycle/failure obligation, reachable implementation, and
ground-truth or discovery role.

## Closed-loop generation

For each episode, the target generator performs:

```text
observe semantic state
-> filter admissible actions
-> choose action and timing
-> execute and collect evidence
-> derive the next semantic state
-> update coverage and corpus
-> continue, terminate, or reset
```

Stateful behavior requires both admissible-action filtering and re-observation
after every action. Precomputing a complete sequence or filtering actions once
is insufficient for the target claim.

## Feedback

The primary online coverage unit is:

```text
(semantic state, action, timing bucket) -> next semantic state
```

The policy gives priority to:

1. admissible executions;
2. new semantic transitions;
3. previously uncovered contract boundaries; and
4. candidates that enter a separate finding-confirmation queue.

Repeated instances of an existing violation signature remain visitation data
but do not create new semantic coverage or receive unbounded reward. Raw
telemetry coverage is diagnostic, not the main feedback abstraction.

## Evidence Admissibility Gate

The collector assigns a contiguous sequence and SHA-256 hash chain. Critical
events retain source time domains and clock-bridge identity. The trace carries
the target-environment attestation registered by the experiment plan.

A trace is inadmissible when it has an invalid chain or sequence, inconsistent
run identity, missing collection bounds, missing required events, a critical
gap, an unmapped clock domain, incomplete route identity, mismatched
environment attestation, or failed plan-specific physical preconditions.

An inadmissible trace produces an overall `INCONCLUSIVE` result. Missing
evidence is never converted into a system `PASS` or `VIOLATION`.

## Contract suite

- Route Conformance checks source revocation, target installation, exclusive
  writers, and actuator-effect continuity.
- Freshness and Lineage checks consumed command age and end-to-end identity
  across the complete target-authority window.
- Successor Progression separately checks completion successor installation,
  explicit fault observation, and complete safe-route installation when a
  fallback is preregistered.
- Registration and Activation checks explicit rejection obligations; lack of
  activation alone is not rejection evidence.

Clause states remain `PASS`, `VIOLATION`, `UNKNOWN`, and `NOT_APPLICABLE`.

## Finding confirmation

Every candidate follows this pipeline:

```text
independent reproduction
-> sequence and timing minimization
-> measurement and instrumentation check
-> signature clustering
-> source/specification attribution
-> full-stack replay for representative cases
```

Reports distinguish research-contract exposure, reproducible contract
violation, source-grounded PX4 defect, and safety-relevant finding. Seeded,
historical, existing natural, and newly discovered natural cases remain
separate categories.

## Full-stack realism

The upper mission and behavior stack supplies trace-derived seeds and verifies
reachability. Search and minimization may run in a controlled harness. A
representative subset is replayed in PX4 SITL with the complete upper software
stack to measure mission and physical consequences. The upper stack is not the
defect target.

## Execution, safety, and cleanup

Formal parallel execution has separate live and offline phases. All live PX4,
Gazebo, ROS, DDS, safety, and raw-collection work in a batch stops before ULog,
clock, Gate, Oracle, compact-evidence, or ledger processing begins. Qualified
formal concurrency remains four.

The supervisor stops an episode on heartbeat or collector loss, clock failure,
non-finite control values, physical boundary violation, or timeout. Cleanup
requires a closed collector, no active external registration or producer
session, a safe internal route, landing when required, and disarming. An
attempt is not accounting-closed until cleanup passes.

## Required comparative method

The main comparison must use a common grammar, seed corpus, reset contract,
observable outcome, and budget for:

- grammar-aware bounded random generation;
- deterministic/systematic enumeration;
- state-conditioned but feedback-free generation; and
- full state- and feedback-guided generation.

Official scenarios are a practice reference. The required core ablations are
feedback removal, route-only versus full semantic state, and timing-only
versus sequence-plus-timing generation. Statistical and execution details are
defined in [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md).
