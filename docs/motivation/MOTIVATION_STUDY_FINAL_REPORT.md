# Motivation Study Final Report

Date: 2026-07-22

Phase: M-FINAL — Unified Motivation Study Completion Gate

Disposition: `CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0`

## 1. Executive Summary

The bounded Motivation Study is **conditionally complete**. Existing evidence
supports the core research Motivation: route conformance, command freshness,
and lifecycle successor progression are coupled flight-safety validation and
software-reliability obligations that are not resolved by mode state or
physical response alone.

This is not a full method-evaluation result. Normal Family A single-event
handoffs are strongly conforming in the frozen baselines, Issue #162 is a
reproducible historical lifecycle benchmark, and one current natural
stale-subject event was re-observed under a phase-dependent condition. The
evidence also leaves three material limits: R1 has no accepted session-rollover
window, W1 has no accepted real-workload source trace, and B1 has no accepted
combined build or runtime controller-graph transition. State-aware search gain
and full fuzzing effectiveness have not been evaluated.

The final Gate therefore authorizes only the creation and push of an
independent **Family A Fuzzer v0 preregistration**. It does not authorize that
campaign's execution.

## 2. Scope and Evidence Cutoff

M-FINAL used only evidence present in `origin/main` at commit
`3665337673e7e0a62ea204ac64f5644b8e428c25`. No flight, PX4, Gazebo, ROS, DDS,
workload, controller, or mutation runtime was started. No campaign was reopened,
and no attempt cap, denominator, threshold, Oracle outcome, acceptance class,
or historical conclusion was changed.

The evidence priority and disposition rules are frozen in the
[M-FINAL preregistration](../../experiments/motivation/m_final/preregistration.yaml).
The complete per-unit audit is the
[evidence ledger](../../experiments/motivation/m_final/evidence_ledger.tsv).

## 3. Repository and Dependency Identity

M-FINAL started from clean `main` with `HEAD == origin/main` at the B1 final
commit. The primary current dependency identity is:

| Component | Identity |
|---|---|
| repository evidence cutoff | `3665337673e7e0a62ea204ac64f5644b8e428c25` |
| PX4 | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| `px4_msgs` | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| `px4-ros2-interface-lib` | `c3e410f035806e8c56246708432ded09c976434b` |
| Route Oracle | `0.4` |
| Freshness Oracle | `0.1` |
| Successor Progression Oracle | `0.1` |
| Authority Event Linearization Oracle | `0.2` |

Issue #162 additionally locks historical PX4
`6ea3539157ca358c70a515878b77077af7d4611d` and interface library
`a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684`. Full hashes and protected artifact
identities are in the [source lock](../../experiments/motivation/m_final/source_lock.yaml).

## 4. M-FINAL Preregistration Identity

The M-FINAL preregistration was committed and pushed before adjudication as
`2f20fb0cf140a27ebdb379a08a176c0a929c6125`. The commit freezes:

- 23 evidence units and the cutoff rule;
- machine Gate → final report → ledger → compact evidence priority;
- eight non-collapsing clause states;
- five mutually exclusive final dispositions;
- MG1–MG10 questions and required outputs;
- Narrative V7 claim boundaries; and
- next-stage preregistration-only authorization.

## 5. Evidence Inventory

The 23 units separate campaign aggregates from materially different evidence
roles:

| Group | Evidence units | Role |
|---|---|---|
| P0 | `P0_NORMAL`, `P0_REENTRY` | normal route and clean re-entry baselines |
| P2/P3 | `P2_PROCESS_LOSS`, `P3_CHANNEL_DECOUPLING` | failure and partial-channel baselines |
| P5 v6 | `P5_TRANSITION`, `P5_RETAINED` | matched mechanism and retained-route evidence |
| Issue #162 | `ISSUE162_BASELINE`, `ISSUE162_CURRENT`, `ISSUE162_HISTORICAL`, `ISSUE162_REDUCED` | legal control, current prevention, historical benchmark, instrumentation differential |
| Freshness | `FRESHNESS_F1`–`FRESHNESS_F4` | setpoint-level exposure and current natural event |
| N1 | `N1_FULL`, `N1_REDUCED` | phase dependence and stability limitation |
| C1/R1 | `C1_MATRIX`, `R1_SESSION` | concurrency grammar and session gap |
| W1 | `W1_SOURCE_AUDIT`, `W1_RUNTIME` | workload scope and unavailable runtime value |
| B1 | `B1_INVENTORY`, `B1_REFERENCE_BUILD`, `B1_RUNTIME` | static mechanism, build block, unavailable runtime generality |

Each row records report, Gate, ledger, compact summary, final commit, SUT
identity, scenario, Oracle, attempt accounting, result counts, evidence role,
and integrity status.

## 6. Evidence Integrity and Consistency Audit

All campaigns with a final machine Gate agree with their formal ledgers on
accepted counts, exclusions, and dispositions. Rejected attempts do not enter a
SUT outcome denominator. Accepted `UNKNOWN` results remain `UNKNOWN`,
`NOT_APPLICABLE` remains distinct from PASS, and Freshness `EXPOSURE` remains
distinct from Route or Successor `VIOLATION`. The Issue #162 reduced run confirms
the same historical finding and is not counted as a new defect.

All source final commits are ancestors of `origin/main`. Protected hashes in
the M-FINAL source lock match. Raw runtime artifacts remain under ignored
namespaces and the tracked raw-file count is zero.

One unresolved but non-blocking structural finding remains. The tracked Issue
#162 `historical_replay_attempt_ledger.yaml` is an early `ACTIVE` checkpoint
rather than a final aggregate ledger. It does not contain the later three
accepted fully instrumented runs or the reduced confirmation. There is no final
Issue #162 machine Gate with which this checkpoint conflicts. Under the frozen
priority, the later final formal report controls, and its counts are
independently supported by four tracked processed `attempt_result.json` files,
each `ACCEPTED`, exact-version locked, and matched to the reported Successor
Oracle outcome. The historical checkpoint is preserved unchanged and this
limitation is not hidden.

P2 and P3 predate the later final-Gate convention. Their formal reports and
tracked 18-row and 24-row matrices agree. P3's five overall Route `UNKNOWN`
results remain visible and are not promoted into its 19 Route PASS count.

## 7. P0/P2/P3 Baselines

P0 Phase A.2 contains nine accepted normal runs: three Offboard, three Dynamic
External Mode, and three Mode Executor. Each accepted transition has a VALID
clock bridge, complete target window, and all five Route Oracle clauses PASS.
P0-D0/D1/D2 additionally establish bounded internal rearm, registration-slot
removal, and one full clean external-to-internal re-entry. These are normal
baselines, not session-rollover results.

P2 contains 18 accepted process-loss cases across Offboard and Dynamic External
Mode with SIGTERM, SIGKILL, and SIGSTOP/SIGCONT. All 18 Route results PASS under
the locked configurations.

P3 contains 24 accepted channel-behavior cases. Health/proof-of-life, rather
than continued setpoint flow alone, controls retained-route versus fallback
selection in the tested matrix. Nineteen overall Route results PASS and five
remain `UNKNOWN` because later cleanup writer windows are bounded. The complete
channel observation does not convert those five route results into PASS.

## 8. P5 v6 Matched Mechanism Baseline

P5 v6 completed 35 matched pairs and 70 accepted sides: 60 transition sides
and 10 retained-route sides. All 70 overall Route results PASS, with zero
accepted `UNKNOWN` or `VIOLATION`. Twenty-five environment attempts are
preserved outside the accepted denominator.

The Gate is `CONDITIONAL_PASS`, not a general safety result. Cross-domain
timing differences were not resolved above clock uncertainty, all cells
triggered an adaptive-repeat reason, and one turn/graceful-shutdown peak-tilt
signal requires confirmation. The 70 PASS sides establish a frozen bounded
baseline only; they do not rank Dynamic External Mode against Offboard.

The 10 retained-route sides have continuity and exclusivity PASS. Their 30
transition-only revocation, installation, and recovery clauses are explicitly
`NOT_APPLICABLE`, not PASS.

## 9. Historical Issue #162 Benchmark

The legal successor control passes in 3/3 accepted current-stack runs. On the
historical affected combination, 3/3 accepted fully instrumented runs and 1/1
accepted reduced-observation run reproduce the same lifecycle failure:
registered executor `1` does not own active External RTL mode `23`, completion
does not advance its schedule, Land is not requested or installed, and the
vehicle remains armed and airborne in the complete window.

Successor Oracle reports all five clauses `VIOLATION`. Route Oracle is
`NOT_APPLICABLE` because no successor transition exists to adjudicate. Current
library `c3e410f` rejects the historical composition during construction before
registration or flight. That prevention is not a current functional successor
PASS.

## 10. Current Freshness Exposure

The frozen pilot closed at 16 attempts with 10 accepted runs and six
observability rejections. Accepted Freshness results are 10 `EXPOSURE`; accepted
Route results are nine PASS and one `VIOLATION`. F2 closed measurement-
insufficient at one accepted run of three planned.

Freshness `EXPOSURE` means that retained commands remain influential without an
explicit enforced per-setpoint freshness policy, or that a bounded physical
exposure threshold is exceeded. It does not automatically identify a software
defect. The single F1 Route violation is a separate post-fallback contract
result.

## 11. N1 Phase-Dependent Natural Event

The original accepted F1 event contains two controller consumptions after
fallback that carry the pre-fallback Trajectory subject timestamp. N1 obtained
eight accepted runs from 14 attempts. Two accepted late-phase runs reproduce
the narrow stale-subject pattern; accepted early and middle phase runs do not.
The one accepted reduced-observation late-phase run is Route PASS.

The final statement is therefore: **the current natural stale-subject event was
re-observed, but it is phase-dependent and not stably reproduced**. No stable
rate, phase-independent trigger, proved root cause, post-revocation old epoch,
external allocator/writer lineage, or actuator-level consequence is claimed.

## 12. C1 Bounded Concurrency Result

C1 has 14 accepted runs from 17 formal attempts. Four event pairs cover all
three frozen timing orders; the activation-plus-Hold near slot is measurement-
insufficient after two observability rejections. Every accepted run passes
Authority Event Linearization Oracle 0.2.

C1 supports a bounded public-event seed grammar and linearization invariant for
the frozen five-pair matrix. It does not establish arbitrary authority-event
concurrency behavior, all scheduler interleavings, or state-aware search gain.

## 13. R1 Session-Rollover Limitation

R1 closed at the R1-A six-attempt cap with zero accepted runs. All six attempts
are `FORMAL_SAFETY_STOP`; no complete new-session window and no Session Rollover
Oracle outcome exists. R1-B and R1-C did not start under the frozen stop rule.

R1 is `MEASUREMENT_INSUFFICIENT`. It is neither a conformance result nor a
session-identity violation. Its unfinished scope is excluded from any Family A
Fuzzer v0 authorization.

## 14. W1 Real-Workload Limitation

The Aerostack2 source/build/interface audit classifies public task interfaces,
route transitions, task-only transitions, and the Native Adapter boundary. It
found no new route or lifecycle semantic that authorized the Native Adapter
spike.

Runtime evidence is unavailable: W1-B has zero accepted source traces from
three formal safety stops; W1-C, W1-D, and W1-E are not applicable and have zero
runtime attempts. W1 is `MEASUREMENT_INSUFFICIENT`. It proves neither that the
workload has runtime added value nor that it lacks such value.

## 15. B1 Family B Static Evidence and Runtime Limitation

B1's revision-locked inventory contains eight subjects, including two true
registered controller routes, `mc_nn` and `mc_raptor`. It also defines and
implements a bounded deterministic partial-subgraph reference and a complete
static observation contract.

B1-D has zero accepted combined builds from three campaign configuration
failures. The reference binary and loadability were not established. B1-E and
B1-F are `NOT_APPLICABLE`, with zero runtime attempts. No runtime registration,
route installation, writer lineage, graph replacement, release, or restoration
claim exists. B1 is `ENVIRONMENT_BLOCKED`, and Family B remains future work.

## 16. MG1–MG10 Adjudication

| Gate | Status | Exact consequence |
|---|---|---|
| MG1 — Unified Problem Existence | `PASS` | core route/freshness/lifecycle problem supported |
| MG2 — Oracle Incremental Value | `PASS` | cross-layer attribution value supported |
| MG3 — Normal Baseline Credibility | `PASS` | bounded Family A baselines credible |
| MG4 — Historical Benchmark Feasibility | `PASS` | exact historical benchmark feasible |
| MG5 — Current Natural Evidence | `CONDITIONAL_PASS` | current event exists but stable reproduction does not |
| MG6 — Partial Failure and Freshness Relevance | `PASS` | measurable channel and command-lineage relevance supported |
| MG7 — Concurrency and Re-entry Readiness | `PARTIAL_PASS` | C1 grammar available; R1 readiness missing |
| MG8 — Real Workload Added Value | `MEASUREMENT_INSUFFICIENT` | runtime added value remains unknown |
| MG9 — Cross-Depth / Family B Generality | `ENVIRONMENT_BLOCKED` | static mechanism exists; runtime generality unsupported |
| MG10 — Attribution and Method-Entry Readiness | `CONDITIONAL_PASS` | bounded Family A method preregistration is ready; effectiveness untested |

The detailed claims, evidence IDs, prohibited stronger claims, and
authorization consequences are machine-readable in the
[final Gate](../../experiments/motivation/m_final/motivation_completion_gate.json).

## 17. Final Motivation Disposition

The preregistered rule selects
`CONDITIONAL_PASS_MOTIVATION_COMPLETE_AUTHORIZE_FAMILY_A_FUZZER_V0`.

MG1–MG4 and MG6 satisfy the core requirements; MG5 supplies an
evidence-complete current finding with a phase-dependence limitation; C1 and
the attribution protocol supply a bounded Family A seed/Oracle entry point.
MG7's R1 gap, MG8's workload gap, MG9's Family B block, and MG10's unevaluated
search gain prevent a full PASS.

## 18. Supported Claims

- Family A is the formal empirical scope of the completed Motivation Study.
- Ordinary single-event Family A handoffs are route-conforming in the frozen
  bounded baselines.
- Route, Freshness, Successor, and Evidence Gates provide distinct detection
  and attribution capability.
- Issue #162 is a historical benchmark with exact current-prevention
  differential.
- A current stale-subject Route event was observed and re-observed under a
  late-phase condition.
- Health/setpoint decoupling and command freshness are relevant to route and
  runtime-consistency validation.
- C1 supplies a bounded event-pair grammar.
- Family B has real static mechanisms and subjects suitable for a future
  independent study.

## 19. Unsupported and Prohibited Claims

M-FINAL does not support general safety rates, mechanism superiority, stable
current-event frequency, a proved current-event root cause, arbitrary
concurrency, session-rollover conformance, real-workload runtime value, Family B
runtime generality, state-aware search gain, or full fuzzing effectiveness.

It is specifically invalid to convert Freshness `EXPOSURE` into `VIOLATION`,
Route `NOT_APPLICABLE` into PASS, accepted Route `UNKNOWN` into PASS, or a
safety/environment/configuration exclusion into a SUT failure.

## 20. Research Scope After M-FINAL

The formal empirical scope is Family A:

```text
PX4 internal route
↔ ROS 2 Offboard
↔ Dynamic External Mode
↔ internal fallback / RTL / Land
```

Family B remains a future independent deep-path validation study. Real workload
runtime value remains a future independent workload study. Neither is imported
into the authorized Family A method entry.

## 21. Recommended Paper Positioning

The paper should be positioned as route, freshness, and lifecycle runtime
verification with a bounded Family A Motivation study, followed by a still-
pending method evaluation. The strongest evidence is not that ordinary handoff
usually fails; it is that mode-level success does not discharge cross-layer
route, command-lineage, lifecycle-owner, and successor obligations.

SaFUZZ is adjacent state-transition fuzzing work organized primarily around:

```text
Application State
× PX4 Flight Mode
× human / failsafe / environmental event
```

This repository instead observes:

```text
Declared Route / Completion / Failure Event
× Runtime Route Instance
× Command Lineage
× Lifecycle Owner
× Controller / Writer Lineage
× Expected Successor / Fallback
```

The distinction is one of tested layer and Oracle object. This study adds
producer session, subject timestamp, executor ownership, writer lineage, and
successor progression observations. It does not claim superiority over SaFUZZ
on every dimension, and its own state-aware fuzzing effectiveness is not yet
evaluated.

## 22. Method-Evaluation Questions Still Pending

The following remain future method questions, not Motivation results:

- state-aware search gain against a random timing baseline;
- known historical benchmark detection;
- current natural-event rediscovery and bounded reproduction;
- R1–R3 realism distribution without importing R1's missing evidence;
- false-positive and evidence-rejection rates;
- campaign yield under a separately frozen attempt cap; and
- full fuzzing effectiveness.

## 23. Next-Stage Authorization

M-FINAL authorizes only this exact action:

> create and push an independent Family A Fuzzer v0 preregistration

That preregistration must freeze its own Family A scope, seeds, provenance,
attempt cap, random comparison, state-aware policy, Oracles, evidence Gate,
stopping rules, and admissibility criteria. No Fuzzer v0 implementation or
runtime begins under M-FINAL.

The authorization excludes real workload runtime, Aerostack2 Native Adapter,
Family B, direct actuator, HITL, real flight, unprovenanced random events, and
any large or full stateful campaign.

## 24. Threats and Limitations

All empirical evidence is tied to frozen SITL versions, one vehicle/world class,
specific setpoints, bounded timing cells, observation patches, clock models,
and acceptance thresholds. Small repeat counts do not estimate population
rates. Environment instability removed attempts from several campaigns.
Cross-domain timing remains limited by clock uncertainty. Some source-backed
mechanisms lack runtime evidence. Physical observations support context and
consequence interpretation, not aircraft-wide safety claims.

## 25. Reproducibility and Artifact Anchors

Primary M-FINAL artifacts are:

- [preregistration](../../experiments/motivation/m_final/preregistration.yaml);
- [source lock](../../experiments/motivation/m_final/source_lock.yaml);
- [evidence ledger](../../experiments/motivation/m_final/evidence_ledger.tsv);
- [MG matrix](../../experiments/motivation/m_final/gate_matrix.yaml);
- [machine Gate](../../experiments/motivation/m_final/motivation_completion_gate.json);
- [compact summary](../../data/processed/motivation/m_final/m_final_summary.json);
- [Gate schema](../../data/schemas/motivation_completion_gate.schema.json); and
- [Narrative V7](../narrative/NEW_NARRATIVE_v7.md).

The automated M-FINAL consistency check validates final artifact existence,
commit ancestry, frozen hashes, Gate/ledger counts, non-collapsing outcome
semantics, authorization fields, Narrative closure, and zero tracked raw files.

## 26. Final Conclusion

The Motivation Study is conditionally complete. It establishes a credible
Family A problem, incremental Oracle value, normal baselines, a historical
benchmark, one phase-dependent current natural event, and a bounded concurrency
grammar. It does not complete the method evaluation, prove search gain, validate
real-workload added value, establish session rollover, or establish Family B
runtime generality.

The only authorized progression is an independent Family A Fuzzer v0
preregistration. All other empirical expansion remains unstarted and
unauthorized.
