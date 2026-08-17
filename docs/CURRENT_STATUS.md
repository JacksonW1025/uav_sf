# Current status

```text
Formal experiment attempts: 200
Retained historical results: 0
Current empirical claims: bounded Thor SITL findings in the final reports
Formal execution environments: primary and supplemental Thor v1 identities
Study state: Stage A1 minimal-mechanism motivation complete and frozen; Stage A2 blocked on physical-validity and runtime qualification
Current work package: Stage A2 readiness and moving-workload Motivation evidence (Phases I--V below)
Paper state after this package: Section 6 Motivation Study complete; Section 7 Main Evaluation still pending
```

Available today: the Family A route model, normalized event contracts,
hash-chained collection, Route Conformance Oracle, Freshness and Lineage
Oracle, Successor Progression Oracle, Evidence Admissibility Gate, controlled
generation strategies, safety supervision, cleanup checking, attempt
accounting, locked sources, a validation/reference container definition, and
non-flight tests.

The primary Thor matrix remains closed at 180 launches: 131 accepted evidence
sets, 20 observability rejections, 28 timeouts, and one environment failure.
Nineteen cells reached target and two invalid-plan cells reached cap. The
separate supplemental study corrected only those plan/fixture contracts and
closed 20/20 new launches as accepted, reaching both 10/10 targets. It does not
change the primary ledger or status.

Across both studies, 200 formal launches are closed and 151 evidence sets are
accepted. Qualification checks remain outside every formal ledger and result.
The V7 narrative also documents a separate prior Orin evidence lineage. Its
source artifacts are not retained on `origin/main`, it is not included in the
Thor counts above, and exact reuse requires separately supplied provenance and
evidence.

The campaign now separates live batches from offline evidence processing.
Four-way remains the qualified formal concurrency after a non-formal 4/5-way
comparison; five-way was not promoted and no new six-way trial was run. The
locked environment and campaign entry are ready for a separately preregistered
official-sequence experiment using the existing live fixture semantics. The
planned Stage A2 moving workload still needs its live fixture, observation
contract, qualification, and separate preregistration. State-aware policy
selection is not yet connected to the live PX4 action backend and therefore
fails closed; no later study or empirical claim is implied.

## Immediate evidence-quality finding

A preliminary read-only inspection of the frozen telemetry found a physical
execution-validity issue that must be recorded before any new formal study.
Twelve of the 151 admissible Stage A1 evidence sets reached no more than
0.08 m above their local-position origin. All 12 belong to the attitude or
body-rate Offboard cells; three have an overall `PASS` and nine have an
overall `VIOLATION`. The nine violating traces contribute ten violation
clauses. This is not a new formal denominator and does not retroactively
change the frozen `94 PASS / 57 VIOLATION` result.

The current fixture latches `ever_airborne` after one
`VehicleLandDetected.landed == false` sample. That condition can be satisfied
by ground-contact fluctuation before the intended public Takeoff has reached a
meaningful altitude. The current Evidence Gate verifies trace and route
evidence but does not distinguish "flew and landed" from "never left the
ground." Consequently:

- the 12 attempts remain part of the Stage A1 result under its frozen plan;
- they must be reported separately in any post-hoc physical analysis;
- Stage A2 may not start until its plan and Gate require sustained takeoff and
  motion-phase completion;
- failed physical preconditions must yield invalid/inconclusive execution,
  never an Oracle `PASS` or `VIOLATION`.

This observation is currently a repository inspection result. It becomes a
paper-facing statement only after a read-only post-hoc analysis records the
input manifest, exact attempts, telemetry rule, digests, and limitations.

## Current work package and paper placement

The current work package is **Phases I--V: Stage A2 readiness and the
moving-workload Motivation study**. It belongs primarily to paper Section 6,
`Motivation Study`. Infrastructure qualification also updates Section 5,
`Implementation`, and the corresponding threats-to-validity discussion. It
does not implement or evaluate the paper's core state-aware generation claim.

| Work | Paper location | Research role | Claim boundary |
| --- | --- | --- | --- |
| Phase I: physical execution audit | Section 6 and Section 8 threats to validity | Qualify what Stage A1 can say about physical behavior | Does not change any Stage A1 attempt, status, threshold, or denominator |
| Phase II: finding/consequence triage | Section 6; RQ4 and RQ5 | Separate concentrated Route findings from motion-dependent physical exposure | A contract violation or trace signature is not automatically a PX4 bug or root cause |
| Phase III: runtime and observation qualification | Section 5 and Section 8 | Protect Evidence Gate validity, probe sensitivity, and reproducibility; strengthen C3/C4 | Qualification attempts remain outside every formal study denominator |
| Phase IV: A2 preregistration and identity freeze | Section 5 evaluation setup | Bind workload, physical validity, safety, timing, observer, and environment before execution | A plan is authorization for only its exact frozen study |
| Phase V: formal matched Stage A2 | Section 6; chiefly RQ5, with bounded support for RQ1/RQ4 | Test whether moving context changes applicable contract states, signatures, or interpretable physical consequences | Does not compare generation strategies or establish a general mechanism safety ranking |
| Phase VI: live backends and fixed-budget comparison | Sections 4 and 7; RQ2/RQ3 | Establish the prospective C6 method contribution and later C7 benchmark | This is the next work package, not part of Stage A2 completion |

Thus, completing Phases I--V closes the paper's Motivation Study. Only
completing Phase VI and its confirmation/ablation work can support the state-aware method
claims in the Main Evaluation.

## Phase I: freeze a physical-execution audit before changing runtime behavior

Create a read-only, digest-bound post-hoc analysis over the 151 frozen
admissible traces. It must:

1. list the 12 non-airborne attempts, their cell, maximum achieved height,
   overall result, and affected clauses;
2. retain the original 151-attempt denominator and report the 139 airborne
   and 12 non-airborne traces as descriptive strata only;
3. align physical telemetry with transition, freshness, successor, and fault
   windows without modifying a closed trace or evaluation;
4. report continuous position, velocity, attitude, body-rate, exposure, and
   recovery measurements where the existing workload makes them identifiable;
5. state that stale constant trajectory targets are physically masked by
   design, while retained attitude/body-rate commands may still have an
   observable signature.

The expected repository artifact is a new post-hoc study directory containing
an analysis plan, input manifest, machine-readable summary, tests, and final
report. It must not edit either Stage A1 formal study directory.

## Phase II: run two distinct offline triage tracks

The root-cause and physical-consequence priorities are intentionally
different.

**Route/root-cause track.** All 11 observed installation violations are in the
attitude setpoint path. Eight of them occur in traces that did become airborne,
so the concentration cannot be dismissed as only the physical-precondition
problem. Reconstruct request, activation, command-consumption, controller,
allocator, and actuator-write timing. Classify the signature as an observer
resolution effect, fixture effect, research-contract finding, or source-level
SUT cause. Do not call it a PX4 bug without a qualified reproduction and
public-spec or source-level grounding.

**Physical-consequence track.** Freshness is the primary A2 exposure
hypothesis. Constant position targets make stale and fresh numerical commands
identical, so absence of trajectory deviation in Stage A1 is not evidence of
harmlessness. Existing airborne attitude/body-rate traces can still be used to
estimate retained-command drift. The output must select one A2 primary
hypothesis before the A2 matrix is frozen.

The eight Dynamic External Mode timeouts outside the invalid RTL fixture also
receive a separate infrastructure diagnosis. Seven share the signature that
the C++ mode received its registration reply while the Python requester never
recorded readiness. This is consistent with a one-shot discovery/reply race,
but the exact DDS cause remains unproven until reproduced.

## Phase III: qualify physical validity, Dynamic readiness, and observer sensitivity

All Phase III changes and flights use a new qualification identity. They are not
executed "under A1" and do not alter the A1 image, configuration, matrices, or
ledgers.

### Physical-validity contract

The next plan/schema and Evidence Gate must bind study-specific execution
preconditions. At minimum they require:

- valid local-position observations;
- a preregistered takeoff height held for a preregistered dwell interval;
- `landed == false` only as one member of a multi-signal airborne predicate;
- entry into the required motion phase and minimum along-track progress before
  a transition or fault is injected;
- required profile coverage for a nominal completion arm.

The fixture must establish the airborne source state through public PX4
actions before it requests the tested route. Merely increasing a constant
attitude/body-rate thrust value is not an acceptable substitute for a robust
takeoff and readiness contract.

### Dynamic requester readiness

Replace dependence on an unrepeatable registration reply with an explicit,
observable readiness handshake or an equivalent retry/query contract. Formal
attempt timing must not start until requester readiness is recorded. The fix
must be exercised under the qualified four-slot load. The qualification sample
size and exit rule must be chosen from the tolerated matched-block loss rate,
not from an arbitrary number of successful examples.

### Observer qualification

Run matched non-formal qualification for three instrument configurations:

1. observation off, used only to measure probe effect and physical/runtime
   equivalence;
2. the Stage A1 baseline profile at approximately 10 Hz;
3. the existing transition profile at approximately 125 Hz.

Compare real-time factor, clock uncertainty, CPU/scheduling load, log volume,
physical trajectory, control-loop behavior, installation/continuity timing,
and evidence yield. The off configuration cannot compute the Route Oracle; it
is only the no-probe reference. Each configuration has a distinct image
identity. The A2 observer is selected and frozen from this result before
formal execution.

Phase III exits only when no physically unexecuted attempt can be admitted as a valid
flight, Dynamic readiness meets its preregistered reliability rule, and the
selected observation profile meets both sensitivity and probe-effect bounds.

## Phase IV: freeze an A2-specific plan and environment

Do not overwrite the Stage A1 method or safety files. Introduce a
backward-compatible plan revision and versioned A2 configuration artifacts.
The formal runner must bind the matrix-selected configuration paths and
digests while continuing to read the frozen Stage A1 schema/configuration.

The A2 plan must bind at least:

- `profile_id` and `profile_digest`;
- position-only versus position-plus-velocity setpoint semantics;
- named motion phases and the logical injection phase;
- physical-validity and profile-coverage requirements;
- `physical_analysis_plan_digest`;
- observer profile and image identity;
- mission envelope, supervisor limits, run/outer timeouts, and cleanup;
- matched-block fields, seeds, accepted-pair targets, and launch caps.

Qualification determines timeout and envelope values. The nominal envelope,
physical-consequence threshold, and safety-supervisor boundary must remain
separate. A safety stop must be preregistered as a censored physical endpoint
or other explicit non-PASS outcome; a severe trace must not disappear merely
because the supervisor intervened.

## Phase V: execute the minimal matched Stage A2

The first A2 workload is deliberately simple and interpretable:

```text
Public Takeoff
    -> stable hover at the qualified altitude
    -> tested external route active
    -> constant-altitude straight-line translation
    -> normal completion or SETPOINT_STALL_HEALTHY
    -> internal Land
```

The moving command is position-only; velocity and acceleration remain unset.
Under a stall, the aircraft therefore retains the last position target instead
of retaining a nonzero velocity command and flying away. A later A2b may study
position-plus-velocity semantics, but it is not mixed into this first causal
experiment.

The formal core has four cells: Legacy Offboard and Dynamic External Mode,
each under normal completion and `SETPOINT_STALL_HEALTHY`. The two mechanisms
share the same profile, logical phase, seed, schedule, successor, observer,
and physical analysis plan. Normal arms target five complete matched blocks;
fault arms target eight. A block with an invalid or missing arm remains in
accounting but does not enter the paired estimate.

The physical layer reports continuous along-track lag, cross-track error,
integrated tracking error, exposure duration/distance, peak motion values, and
recovery after successor installation. It is hash-bound to the formal inputs
and trace but remains separate from the four correctness Oracles; it does not
become a fifth Oracle or change the Stage A1 thresholds.

The official A2 workload should pass through the same generic
decision/schedule/action/request/effect executor that later strategies will
use. This makes A2 the first live backend vertical slice without turning A2
itself into a strategy comparison.

## Required end state of this work package

### Repository state

When Phases I--V are complete, the repository must contain:

- untouched Stage A1 primary and supplemental plans, ledgers, compact results,
  thresholds, statuses, and `200 / 151 / 94 / 57` accounting;
- a reproducible physical-execution audit that explicitly records the 12
  non-airborne traces and limits their physical interpretation;
- a digest-bound triage result for attitude installation and freshness
  exposure, including unresolved classifications where evidence is
  insufficient;
- a backward-compatible plan/schema path for workload and physical-validity
  bindings, plus separate versioned A2 method and safety configurations;
- tests proving that absent takeoff or absent required motion is never admitted
  as a valid flight result;
- a qualified Dynamic readiness contract and a frozen off/10 Hz/125 Hz
  observer-sensitivity decision;
- a new attested A2 repository revision, container image, PX4 binary,
  environment identity, preregistration, matrix, hash-chained ledger, compact
  evidence, matched-differential result, physical-consequence result, and final
  report;
- a generic official-sequence action-executor vertical slice ready to accept a
  later bounded-random schedule;
- a clean worktree and a complete repository-validation pass.

### Narrative and paper state

At the same milestone, the narrative must say:

```text
Stage A1: COMPLETE WITH BOUNDED CLAIMS; frozen and unchanged
Stage A2: COMPLETE under its own preregistration, identity, ledger, and denominator
Paper Section 6 Motivation Study: COMPLETE
Paper Section 7 Main Evaluation: PENDING
Gate 4b moving-workload realism bridge: PASS WITH BOUNDED CLAIMS, retaining a null result if observed
Gates 5--8 and contributions C6/C7: still PENDING
```

Stage A2 completion depends on admissible execution and honest reporting, not
on obtaining a positive result. A null result must be retained if movement
adds no new signature or measurable consequence. If it does add evidence, the
allowable claim is bounded to the locked Thor SITL mission and may state that
motion context changed contract applicability, violation signatures, or
physical exposure. It may not claim real-flight danger, a general PX4 defect
rate, universal mechanism superiority, or state-aware search effectiveness.

After this milestone, the next work package is Phase VI: connect bounded-random and
state-aware to the shared live executor, qualify decision/schedule/request/
effect replay, run the fixed-budget three-strategy campaign, and then cluster,
reproduce, and minimize findings. Only that work can move paper Section 7,
RQ2/RQ3, Gate 5--8, and prospective contributions C6/C7 to complete.

For a beginner-oriented explanation of the repository narrative, the concrete
Stage A1 flight workloads, Runtime Route Instance, and a complete transition,
see [REPOSITORY_UNDERSTANDING_GUIDE.md](REPOSITORY_UNDERSTANDING_GUIDE.md).
