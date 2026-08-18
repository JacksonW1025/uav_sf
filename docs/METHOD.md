# Method

This file separates the V8 target method from the partial components retained
after repository consolidation. The rationale is defined in
[NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md), completed facts in
[CURRENT_STATUS.md](CURRENT_STATUS.md), and implementation order in the
[experiment plan](EXPERIMENT_PLAN.md).

## Target method

The target is evidence-gated, route-state-guided generation for PX4 authority
handoffs. It combines:

1. independently supported cross-layer observation and semantic-state
   extraction;
2. combined evidence admissibility and a layered contract suite;
3. a reachable action grammar with lifecycle and safety preconditions;
4. closed-loop action-sequence and timing selection;
5. semantic-transition and contract-boundary feedback;
6. independent reproduction, minimization, clustering, and attribution; and
7. representative full-stack consequence replay.

The generation method is the paper headline. Observation, Gate, Oracle, and
finding confirmation are necessary support; they cannot substitute for a
comparative method result.

## Current implementation boundary

Stage 0 repository consolidation is complete. The checkout retains only
partial, V8-relevant primitives:

- the route-event and Runtime Route Instance skeleton;
- raw hash-chained collection, clock fitting, and ULog field extraction;
- Route, Freshness/Lineage, Successor, and Registration Oracle primitives;
- append-only accounting, safety/cleanup, artifact hashing, isolation, and
  physical-takeoff helpers; and
- in-scope Stage A2 and ROS/PX4 workload components.

It deliberately has no active normalized-trace closure, plan/result schema,
semantic-state extractor, combined admissibility Gate, finding state machine,
observation patch, flight image, campaign runner, evaluator, or formal matrix.
No retained component is an executable V8 method.

The completed 18-launch timing slice is evidence that one bounded feedback
prototype was executable in its frozen environment. Its policy, runner, and
configuration are not active V8 implementation.

## Observation and identity contract

The target Runtime Route Instance has ten stable fields:

```text
(route, route_epoch, producer_session, registration_id, activation_id,
 controller_id, allocator_id, writer_id, lifecycle_owner, executor_owner)
```

Every normalized field must carry provenance:

- `OBSERVED`: independently emitted at the claimed boundary;
- `DERIVED`: deterministically computed from observed fields under a frozen
  rule that does not encode the expected result;
- `INFERRED`: a hypothesis that cannot establish a correctness obligation;
- `CONSTANT`: configuration metadata that cannot prove runtime identity.

The earlier closure derived or fixed several identity fields and converted one
actuator-output event into both allocator and writer events. That closure was
removed. The new contract must provide independent allocator publication and
writer/effect boundaries, and it must require complete identity on every
authority-bearing lifecycle/effect event.

## Semantic state

After the observation contract closes, the extractor derives:

- route identity, family, and epoch;
- authority owner and downstream lineage;
- registration, activation, execution, completion, replacement, fallback,
  and re-entry phase;
- health and command freshness;
- successor request, installation, and ownership progression;
- coarse physical/mission context; and
- bounded action history for the current episode.

Equivalent evidence must produce deterministic state. A reduced-observation
replay must quantify dependence on custom instrumentation.

## Combined evidence admissibility

The final overall decision composes, without short-circuiting away diagnostic
detail:

```text
TRACE_INTEGRITY
+ IDENTITY_PROVENANCE
+ CLOCK_CLOSURE
+ ENVIRONMENT_MATCH
+ REQUIRED_EVENT_COVERAGE
+ PHYSICAL_VALIDITY
-> OVERALL_ADMISSIBLE | INCONCLUSIVE
```

The retained `scripts/oracles/evidence_gate.py` is only a trace-level
prototype. It does not include the complete authority-event or physical
contract and cannot authorize a V8 result. Contract Oracles run only after
`OVERALL_ADMISSIBLE` passes.

## Contract suite

- **Route Conformance**: source revocation, target installation, writer
  exclusivity, and effect continuity.
- **Freshness and Lineage**: command age and consistent producer-to-writer
  lineage across the complete authority window.
- **Successor Progression**: completion successor, planned-fault observation,
  and complete safe-fallback installation.
- **Registration and Activation**: explicit rejection obligations; absence of
  activation is not rejection evidence.

Clause states remain `PASS`, `VIOLATION`, `UNKNOWN`, and `NOT_APPLICABLE`.
They are contract outcomes, not automatically findings.

## Finding confirmation

Each candidate follows a recorded state machine:

```text
CANDIDATE
-> REPRODUCED
-> MINIMIZED
-> CLUSTERED
-> ATTRIBUTED
-> FULL_STACK_REPLAYED (when selected)
```

Reports keep four interpretation levels separate:

1. research-contract exposure;
2. reproducible cross-layer contract violation;
3. source-grounded PX4 defect; and
4. safety-relevant finding with reproducible full-stack consequence.

Historical, seeded, confirmed-current, and newly discovered natural origins
remain separate. Formal-run candidates cannot be fed back into the same run's
frozen benchmark.

## Realistic action corpus

Candidate actions are organized by lifecycle phase and authority/failure
mechanism. Every included action records provenance, reachable preconditions,
observable request/effect boundaries, cleanup, safety limits, reality distance,
and benchmark/discovery role.

The upper mission/behavior stack is integrated before corpus freeze to supply
traces, parameter ranges, and reachability evidence. Controlled harnesses may
search and minimize. A preregistered representative subset returns to the full
stack for consequence replay.

## Closed-loop generation and feedback

For each episode:

```text
observe semantic state
-> filter admissible actions
-> select action and timing
-> execute
-> recompute overall admissibility
-> observe the next semantic state
-> update coverage/corpus only if admissible
-> continue, terminate, or reset
```

The primary online unit is:

```text
(semantic state, action, timing bucket) -> next semantic state
```

Repeated instances of one candidate remain visitation data; they do not create
unbounded reward or distinct confirmed findings.

## Comparative methods

The core comparison uses a common action grammar, seed corpus, reset contract,
outcome contract, safety rules, and execution budget for:

- grammar-aware bounded random generation;
- deterministic/systematic enumeration;
- state-conditioned but feedback-free generation; and
- full state- and feedback-guided generation.

Official or handwritten scenarios are a separate practice reference. Required
core ablations are feedback removal, route-identity-only versus full semantic
state, and timing-only versus action-sequence-plus-timing generation.

## Execution and statistics

One adaptive campaign, starting with empty generator memory, is the independent
statistical unit. Episodes and launches inside a campaign are correlated.
Paired seeds, budgets, reset semantics, effect sizes, uncertainty, and stopping
rules are frozen after pilot work and before formal execution.

No concurrency value carries forward automatically from the retained runtime.
The new V8 image and workload require serial-versus-parallel interference
qualification. Live work on an experiment host must not overlap offline ULog,
clock, Gate, Oracle, or reporting work from any batch.

Implementation must follow the gates in
[EXPERIMENT_PLAN.zh-CN.md](EXPERIMENT_PLAN.zh-CN.md). Readiness at one gate never
authorizes a later gate.
