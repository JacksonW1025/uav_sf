# Current research scope

The current topic is **Testing Route-Replacing Authority Transitions in PX4**.
M-FINAL conditionally completed the bounded Motivation Study at evidence cutoff
`3665337673e7e0a62ea204ac64f5644b8e428c25`.

The central question is whether a declared transfer from Route A to Route B is
reflected by the complete runtime control path:

1. the old path is revoked promptly;
2. the new path is completely installed;
3. the transition window remains exclusive and continuous;
4. the safe path is completely restored after failure.

For executor-owned routes, the declared handoff contract also includes the
Successor Progression Contract: the registered lifecycle owner and executor
owner must receive completion and request/install the expected successor.
Route Oracle checks control-path revocation/installation; Successor Oracle
checks ownership, completion delivery, and successor progression. The two
contracts are complementary and are not substituted for one another.

## Subject families

**Family A — formal empirical scope**

```text
PX4 Internal Route
↔ ROS 2 Offboard
↔ Dynamic External Mode
↔ Internal Fallback / RTL / Land / RC takeover
```

**Family B — static evidence and future independent study**

```text
PX4 Classical Cascade
↔ Registered Learned Controller
↔ Classical Fallback
```

The locked B1 inventory proves that `mc_nn` and `mc_raptor` are true registered
controller routes and that a bounded partial-subgraph reference contract can be
defined. B1 has no accepted combined build or runtime evidence. Family B is not
part of the current runtime generality claim and is not authorized for the next
phase.

## Completed Motivation sequence

```text
Repository recovery and route observability (complete)
→ P5 v6 bounded differential campaign (complete and frozen)
→ Motivation Case 1: Issue #162 successor failure (complete and frozen)
→ Current-version External Mode setpoint freshness bounded pilot (complete and frozen)
→ N1 / C1 / R1 / W1 / B1 bounded closure (complete and frozen)
→ M-FINAL: CONDITIONALLY_COMPLETE
```

The final Motivation disposition is
`CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0`.
It authorizes only creation and push of an independent Family A Fuzzer v0
preregistration. It does not authorize implementation or execution.

| Evidence area | Final scope status |
|---|---|
| Family A normal route conformance | bounded formal empirical support |
| current natural event | re-observed but phase-dependent |
| C1 concurrency | bounded event-pair conformance only |
| R1 session rollover | `MEASUREMENT_INSUFFICIENT` |
| W1 real-workload runtime value | `MEASUREMENT_INSUFFICIENT` |
| Family B static mechanism | supported |
| Family B runtime generality | `ENVIRONMENT_BLOCKED`; future work |
| state-aware search gain | not evaluated |
| full fuzzing effectiveness | not evaluated |

The next phase must exclude R1's unfinished session scope, Aerostack2 runtime,
Family B, direct actuator, HITL, real flight, unprovenanced random events, and
large or full stateful campaigns unless a later independent registration
explicitly authorizes them.

The independent Family A Fuzzer v0 preregistration remains frozen and
`PREREGISTERED_NOT_ACTIVATED`. Its qualification activation review decided
`DECLINE_IMPLEMENTATION_NOT_READY`; qualification and all comparison arms are
unauthorized, and formal attempts remain zero. The next exact action is to
create an independent amendment or readiness-resolution plan for the recorded
blockers. No Family A Fuzzer v0 runtime has executed.
