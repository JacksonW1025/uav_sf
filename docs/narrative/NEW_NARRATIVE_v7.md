# Testing Route-Replacing Authority Transitions in PX4 — Narrative V7

Status: current after M-FINAL

Evidence cutoff: `3665337673e7e0a62ea204ac64f5644b8e428c25`

Motivation disposition:
`CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0`

## 1. Central Research Position

PX4 uses several mechanisms to select and execute flight-critical command
paths: internal modes, ROS 2 Offboard, Dynamic External Modes, Mode Executors,
fallback logic, and registered onboard controllers. A declared mode change is
only one part of a complete runtime transition. The software must also revoke
the old command path, install the new one, preserve exclusivity and continuity,
and advance the correct lifecycle owner toward the expected successor.

This work studies **route-replacing authority transitions**:

> A flight-critical control route changes from Route A to Route B, so the old
> route must cease influence, the new route must become complete and exclusive,
> and failure or completion must progress to the expected fallback or
> successor.

The M-FINAL evidence changes the emphasis of the research story. In frozen
normal single-event scenarios, PX4 shows strong route conformance. The research
value does not come from a claim that ordinary handoffs generally fail. It
comes from three cross-layer obligations that mode state and physical response
alone cannot discharge:

1. route revocation, installation, exclusivity, continuity, and recovery;
2. command freshness and lineage; and
3. lifecycle ownership and successor progression.

The Motivation Study is conditionally complete for Family A. Full method
evaluation is still pending.

## 2. Runtime Route Model

A route is a runtime instance, not merely a module name:

```text
RouteInstance = (
    declared mode and authority,
    route epoch,
    producer session,
    registration and activation instance,
    command subject timestamp and lineage,
    controller graph,
    allocator participation,
    actuator writer lineage,
    lifecycle owner and executor owner,
    expected successor or fallback
)
```

The expected transition is compared with the observed runtime path:

```text
Declared Route / Completion / Failure Event
                    versus
Observed Route Instance / Command Lineage / Owner / Writer / Successor
```

This distinction matters because a shared downstream module such as
`control_allocator` can participate in several routes. A writer name without a
route epoch and upstream lineage does not prove route identity. Likewise,
`nav_state` can identify a selected mode while leaving completion delivery,
executor ownership, or successor installation unresolved.

## 3. Three Complementary Contracts

### 3.1 Route Conformance

The route contract checks:

- old-route producer, consumption, allocator, and writer revocation;
- complete target producer/controller/writer installation;
- absence of an illegal owner or writer overlap;
- absence of a policy-exceeding route gap; and
- fallback installation and old-route non-return.

Route Oracle 0.4 returns only `PASS`, `VIOLATION`, `UNKNOWN`, or
`NOT_APPLICABLE`. Missing evidence never becomes PASS.

### 3.2 Command Freshness and Lineage

The freshness contract evaluates the interval after valid setpoint publication
stops and before fallback or bounded policy termination. It distinguishes:

- the producer's last publication;
- PX4 receive time;
- controller use of the command subject;
- allocator and writer influence carrying that lineage;
- health-loss and fallback timing; and
- bounded physical context.

Freshness `EXPOSURE` describes retained command use without an explicit
enforced policy sufficient for a contract violation, or a bounded physical
exposure. It is not automatically a defect. A separate post-revocation Route
violation can coexist with a pre-revocation Freshness `EXPOSURE`.

### 3.3 Lifecycle Ownership and Successor Progression

For executor-owned routes, a successful behavior is incomplete unless the
right owner receives completion and progresses the mission:

```text
registered owner
→ active executor owner
→ completion generated and delivered
→ expected successor requested
→ successor selected and installed
→ terminal mission state
```

Successor Progression Oracle 0.1 checks this chain independently of Route
Oracle. When no successor is requested, Route Oracle can correctly return
`NOT_APPLICABLE` while Successor Oracle reports a lifecycle `VIOLATION`.

## 4. Formal Empirical Scope

### 4.1 Family A — formal scope

```text
PX4 Internal Route
↔ ROS 2 Offboard
↔ Dynamic External Mode
↔ Internal Hold / RTL / Land / Recovery
```

Family A has accepted evidence for normal entry and release, process loss,
health/setpoint decoupling, matched mechanism comparisons, historical successor
behavior, current freshness behavior, phase-dependent natural evidence, and a
bounded concurrency matrix.

### 4.2 Family B — future work

```text
PX4 Classical Cascade
↔ Registered Onboard Controller Route
↔ Classical Fallback
```

The B1 source inventory proves that two true registered-controller routes exist
in the locked PX4 tree: `mc_nn` and `mc_raptor`. The deterministic B1 reference
also establishes a static partial-subgraph route contract and observation
design. However, no accepted combined reference build exists, and no runtime
registration, installation, writer-lineage, release, or restoration window was
executed. Family B therefore remains `future_work` and is outside the current
runtime generality claim.

## 5. Normal Route-Conformance Baselines

P0 Phase A.2 supplies nine accepted normal runs across Offboard, Dynamic
External Mode, and Mode Executor. Each accepted target transition has a VALID
clock bridge, complete window, and all five Route clauses PASS. P0-D0/D1/D2
add bounded internal rearm, registration-slot removal, and one clean external
re-entry.

P2 supplies 18 accepted process-loss cases across two mechanisms and three
locally controlled failure classes. Every accepted Route result PASSes for the
frozen fallback configuration.

P3 supplies 24 accepted health/setpoint channel-behavior cases. It establishes
that health or proof-of-life controls route retention independently from
setpoint flow in the tested matrix. Five overall Route results remain
`UNKNOWN` because later cleanup writer windows are bounded; those results are
not counted as PASS.

P5 v6 supplies 35 matched pairs and 70 accepted sides. All 70 overall Route
results PASS, with zero accepted `UNKNOWN` or `VIOLATION`. Ten retained-route
sides PASS continuity and exclusivity while their transition-only clauses are
explicitly `NOT_APPLICABLE`.

These results form a strong bounded baseline. They do not establish a general
safety rate, a population probability, or a mechanism-wide safety ranking.
Cross-domain timing differences remain unresolved above clock uncertainty, and
one turn/graceful-shutdown physical signal requires confirmation.

## 6. Historical Lifecycle Benchmark

Issue #162 is a historical benchmark, not a current executable defect.

The legal non-replacement control completes the expected owner → completion →
Land → Disarm chain in 3/3 accepted runs. On the exact historical affected
combination, 3/3 accepted fully instrumented runs and 1/1 accepted reduced-
observation run reproduce one lifecycle failure:

```text
External RTL selected and reaches its target
→ registered executor 1 is not in charge
→ successful completion does not advance executor 1
→ Land is not requested or installed
→ vehicle remains armed and airborne in External RTL
```

Successor Oracle reports all five clauses `VIOLATION`. Route Oracle is
`NOT_APPLICABLE` because no Land transition is created. The current interface
library prevents this historical composition in the constructor before
registration or flight. That guard is prevention, not proof that the same
functional successor chain works on the current version.

## 7. Current Command-Freshness Evidence

The current-version Freshness pilot closed at 16 attempts with 10 accepted
runs. All accepted Freshness results are `EXPOSURE`; accepted Route results are
nine PASS and one `VIOLATION`. The Attitude process-stop cell closed
measurement-insufficient at one accepted run of three planned.

The evidence supports a design/policy statement: when no enforced per-setpoint
freshness deadline applies, a retained command can continue to influence the
controller until health-driven fallback, or through a bounded health-alive
setpoint-stall window. This is relevant to runtime consistency. It is not a
blanket defect label.

## 8. Current Natural Stale-Subject Event

Accepted run `freshness-f1-a02` records two controller consumptions after
fallback carrying the pre-fallback Trajectory subject timestamp. The fallback
route itself is installed, and there is no post-revocation old route epoch,
external allocator input, or external writer output.

N1 re-observed the same narrow pattern in two accepted late-phase runs. Five
accepted early/middle-phase runs did not show it, and the one accepted
reduced-observation late-phase run is Route PASS.

The final current-event statement is deliberately narrow:

> A current natural post-fallback stale-subject event was observed and
> re-observed under a late phase bucket; it is phase-dependent and not stably
> reproduced.

The evidence does not establish a stable occurrence rate, a phase-independent
failure, a proved source root cause, external actuator authority after fallback,
or a general physical consequence.

## 9. Bounded Concurrency and Re-entry

C1 tests five public authority-event pairs under event-A-first, near, and
event-B-first orders. It closes with 14 accepted runs from 17 attempts. Four
pairs have complete three-order coverage; activation-plus-Hold near is
measurement-insufficient. Every accepted result passes the frozen linearization
Oracle.

C1 therefore supports a bounded event-pair grammar and a final-route
linearization invariant. It does not prove all concurrency combinations,
scheduler interleavings, or timing regions.

R1 is different. It closes with zero accepted session-rollover runs after six
formal safety stops. No Session Rollover Oracle result exists, and later R1
scenarios did not start under the frozen stop rule. P0 clean re-entry must not
be relabeled as session rollover. R1 remains a measurement gap and is excluded
from the authorized Family A method scope.

## 10. Real-Workload Evidence Boundary

The W1 Aerostack2 source/interface audit identifies public task services,
actions, motion references, Offboard production, aircraft Land, and task-only
transitions. It also concludes that the Native Adapter adds no source-proved
route or lifecycle semantic beyond the Canonical Adapter for this bounded Gate.

No accepted runtime source trace exists. W1-B reaches zero accepted traces at
its three-attempt cap, and dependent trace-only, Canonical, and Native runtime
phases are not applicable. Thus real-workload runtime added value remains
unknown. W1 cannot be used to claim either that a real workload adds value or
that it does not. It is not part of the completed core empirical contribution.

## 11. What the Motivation Study Establishes

The M-FINAL Gate adjudicates:

| Clause | Result |
|---|---|
| Unified Problem Existence | `PASS` |
| Oracle Incremental Value | `PASS` |
| Normal Baseline Credibility | `PASS` |
| Historical Benchmark Feasibility | `PASS` |
| Current Natural Evidence | `CONDITIONAL_PASS` |
| Partial Failure and Freshness Relevance | `PASS` |
| Concurrency and Re-entry Readiness | `PARTIAL_PASS` |
| Real Workload Added Value | `MEASUREMENT_INSUFFICIENT` |
| Cross-Depth / Family B Generality | `ENVIRONMENT_BLOCKED` |
| Attribution and Method-Entry Readiness | `CONDITIONAL_PASS` |

Accordingly:

- core Motivation is supported;
- Family A has formal empirical support;
- Family B has static mechanism support only;
- real-workload runtime added value remains unknown;
- current natural evidence is phase-dependent;
- state-aware search gain is untested; and
- full fuzzing effectiveness is untested.

## 12. Research Questions After M-FINAL

The completed Motivation evidence supports these current questions:

1. Can a bounded state-aware method find route, freshness, or lifecycle
   outcomes more effectively than a random timing baseline?
2. Can it detect the frozen historical benchmark without changing that
   benchmark's evidence?
3. Can it rediscover or reproduce the phase-dependent current natural event
   under a registered cap?
4. What proportion of generated attempts remains admissible under clock,
   lineage, window, safety, and cleanup requirements?
5. What false-positive and evidence-rejection behavior results from combining
   Route, Freshness, Successor, and Evidence Gates?

These are future method-evaluation questions. Narrative V7 does not predeclare
their results.

## 13. Method Entry Boundary

M-FINAL authorizes only the next preregistration:

```text
Independent Family A Fuzzer v0 preregistration
```

That document must independently freeze:

- Family A route and lifecycle scope;
- supported seeds and event provenance;
- state-aware and random timing baselines;
- attempt caps and stopping rules;
- Route, Freshness, Successor, and Evidence Gate versions;
- known-benchmark and natural-event evaluation rules;
- R1–R3 realism distribution boundaries;
- false-positive and evidence-rejection metrics; and
- cleanup and flight-safety limits.

M-FINAL does not start implementation or execution. It does not authorize a
large campaign, Family B runtime, real workload runtime, direct actuator,
HITL, real flight, or unprovenanced random event.

## 14. Relationship to SaFUZZ

SaFUZZ is adjacent state-transition fuzzing work organized primarily around:

```text
Application State
× PX4 Flight Mode
× human / failsafe / environmental event
```

This work is organized around:

```text
Declared Route / Completion / Failure Event
× Runtime Route Instance
× Command Lineage
× Lifecycle Owner
× Controller / Writer Lineage
× Expected Successor / Fallback
```

The methods inspect different layers and Oracle objects. This work adds
producer-session identity, subject timestamp, executor ownership, writer
lineage, and successor progression to the observed contract. SaFUZZ remains
relevant adjacent state-transition work. Narrative V7 does not claim that this
approach is better on every dimension, and it does not claim completed
state-aware fuzzing effectiveness.

## 15. Supported Contribution Framing

The evidence supports the following contribution framing:

1. **Problem formulation:** route-replacing authority transitions unify
   companion-side mode/producer changes under cross-layer runtime obligations.
2. **Runtime model:** route instance, command lineage, lifecycle owner,
   controller/writer lineage, and expected successor refine mode state.
3. **Complementary Oracles:** Route, Freshness, Successor, and Evidence Gates
   separate conformance, exposure, lifecycle progression, and admissibility.
4. **Bounded Family A Motivation study:** normal baselines, historical
   benchmark, current phase-dependent finding, and deterministic concurrency
   grammar.
5. **Pending method evaluation:** state-aware search gain, random baseline,
   benchmark detection, natural rediscovery, and rejection analysis remain to
   be measured.

It does not yet support a contribution framed as a completed full fuzzer, a
cross-family runtime study, a validated real-workload study, or a general
safety comparison between mechanisms.

## 16. Claim Guardrails

Supported:

- bounded Family A normal route conformance;
- incremental cross-layer Oracle value;
- one historical lifecycle benchmark;
- current freshness exposure;
- a phase-dependent current natural Route event;
- bounded C1 event-pair conformance;
- static existence of Family B registered-controller routes; and
- evidence-admissibility discipline for later bounded evaluation.

Unsupported or prohibited:

- P5 as a general safety proof;
- Freshness `EXPOSURE` as an automatic defect;
- current natural-event stability, frequency, or known root cause;
- Issue #162 as a current executable bug;
- `NOT_APPLICABLE` or `UNKNOWN` as PASS;
- C1 as proof of all concurrent authority behavior;
- R1 session rollover as PASS or SUT failure;
- W1 as proof of real-workload value or lack of value;
- B1 as Family B runtime validation;
- Dynamic External Mode as safer than Offboard;
- state-aware search gain as demonstrated; or
- full fuzzing effectiveness as completed.

## 17. Future Work After the Authorized Preregistration

Only if a separate preregistration authorizes it, the Family A method study may
evaluate:

- state-aware search gain;
- a random timing baseline;
- known benchmark detection;
- natural-event rediscovery and bounded reproduction;
- R1–R3 realism distribution;
- false-positive and evidence-rejection behavior; and
- bounded campaign effectiveness.

Separately scoped future studies may revisit real-workload runtime value and
Family B runtime graph replacement. They are not dependencies silently added
to Family A Fuzzer v0.

## 18. Final Narrative

PX4 is strongly route-conforming in the frozen normal Family A scenarios, but
mode-level success does not by itself prove that commands are fresh, the right
lifecycle owner advances, or the expected successor is installed. The
historical benchmark shows a route that executes while mission progression
dead-ends. The current study shows a command-freshness policy exposure and a
narrow stale-subject Route event whose occurrence depends on phase. The
concurrency study shows that a bounded public-event grammar can be adjudicated,
while R1, W1, and B1 preserve important measurement and environment limits.

The resulting research position is precise: complete the Motivation Study at a
conditional Family A boundary, then evaluate—rather than assume—the value of a
state-aware search method. Family B and real workloads remain future independent
validation subjects. The next exact action is to create and push the independent
Family A Fuzzer v0 preregistration; nothing in Narrative V7 claims that phase
has started.

## 19. Primary Artifact Anchors

- [M-FINAL final report](../motivation/MOTIVATION_STUDY_FINAL_REPORT.md)
- [M-FINAL machine Gate](../../experiments/motivation/m_final/motivation_completion_gate.json)
- [M-FINAL evidence ledger](../../experiments/motivation/m_final/evidence_ledger.tsv)
- [Route Epoch Model](../design/ROUTE_EPOCH_MODEL.md)
- [Route Oracle](../design/ROUTE_ORACLE_V0.md)
- [Freshness Oracle](../design/PRE_REVOCATION_FRESHNESS_ORACLE.md)
- [Successor Progression Oracle](../design/SUCCESSOR_PROGRESSION_ORACLE.md)
- [Clock Bridge](../design/CLOCK_BRIDGE_IMPLEMENTATION.md)
