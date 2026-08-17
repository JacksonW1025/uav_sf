# Current status

```text
Formal Thor launches retained across completed and closed studies: 295
Retained historical results: 0
Current empirical claims: bounded Thor SITL findings in the final reports
Formal execution environments: Stage A1 primary/supplemental, Stage A2 primary/remediation, and Main strategy-comparison Thor identities
Study state: Stage A1 frozen; Stage A2 complete; the 18-launch live-strategy vertical slice complete with bounded claims
Completed work package: Stage A2 Motivation evidence plus the first Main Evaluation vertical slice (Phases I--VI below)
Active phase: expand Section 7 beyond one action, then confirm/cluster/minimize findings
Paper state: Section 6 Motivation Study complete; Section 7 Main Evaluation partially complete, not paper-complete
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

Stage A2 adds 77 closed formal launches under two separate studies. Its primary
study remains `MEASUREMENT_INSUFFICIENT` at 51 launches: 18 accepted, 31
observability-rejected, and two inconclusive. The independent remediation
closed 26/26 launches as accepted and admissible, reaching all four frozen
targets without modifying the primary ledger. Its 10 normal traces are overall
PASS and its 16 deliberate healthy-stall traces are overall VIOLATION only on
freshness. Counts are reported per study and are not pooled into the Stage A1
`200 / 151 / 94 / 57` result.

The first Section 7 strategy study adds a separate fixed denominator of 18
formal launches: two mechanisms by three strategies by three launches. All
18 are closed, accepted, Evidence Gate admissible, physically valid, and
overall `VIOLATION` only on freshness. These counts are not pooled into either
Stage A1 or Stage A2. The complete formal Thor total is therefore 295 launches.

The campaign now separates live batches from offline evidence processing.
Four-way remains the qualified formal concurrency after a non-formal 4/5-way
comparison; five-way was not promoted and no new six-way trial was run. The
locked environment and campaign entry are ready for separately preregistered
experiments using qualified live fixture semantics. Stage A2 has its own
implemented fixture, observation contract,
qualification, preregistration, formal evidence, physical analysis, and final
report. Phase VI adds a shared state-conditioned setpoint-stall executor for
official sequence, bounded random timing, and state-aware selection. Its
18-launch result is a Section 7 vertical slice, not a general
search-effectiveness result.

## Resolved Stage A2 evidence-quality prerequisite

A completed read-only, digest-bound audit of the frozen telemetry found a
physical execution-validity issue that was addressed before Stage A2 formal execution.
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
- Stage A2 was not allowed to start until its plan and Gate required sustained
  takeoff and motion-phase completion;
- failed physical preconditions must yield invalid/inconclusive execution,
  never an Oracle `PASS` or `VIOLATION`.

The paper-facing post-hoc record is frozen in
[`experiments/posthoc_physical_execution_validity_v1/`](../experiments/posthoc_physical_execution_validity_v1/).
It records the analysis plan, input manifest, exact attempts, aligned physical
windows, telemetry digests, generated summary, tests, and interpretation
limits. Reproduction from an empty output directory is byte-identical.

## Completed evidence package and current paper placement

The completed evidence package is **Phases I--VI: Stage A2 readiness and
moving-workload Motivation evidence, followed by one fixed-budget live-strategy
vertical slice**. Phases I--V belong primarily to paper Section 6,
`Motivation Study`; Phase VI belongs to Sections 4 and 7. Infrastructure
qualification also updates Section 5, `Implementation`, and the corresponding
threats-to-validity discussion.

| Work | Paper location | Research role | Claim boundary |
| --- | --- | --- | --- |
| Phase I: physical execution audit | Section 6 and Section 8 threats to validity | Qualify what Stage A1 can say about physical behavior | Does not change any Stage A1 attempt, status, threshold, or denominator |
| Phase II: finding/consequence triage | Section 6; RQ4 and RQ5 | Separate concentrated Route findings from motion-dependent physical exposure | A contract violation or trace signature is not automatically a PX4 bug or root cause |
| Phase III: runtime and observation qualification | Section 5 and Section 8 | Protect Evidence Gate validity, probe sensitivity, and reproducibility; strengthen C3/C4 | Qualification attempts remain outside every formal study denominator |
| Phase IV: A2 preregistration and identity freeze | Section 5 evaluation setup | Bind workload, physical validity, safety, timing, observer, and environment before execution | A plan is authorization for only its exact frozen study |
| Phase V: formal matched Stage A2 | Section 6; chiefly RQ5, with bounded support for RQ1/RQ4 | Test whether moving context changes applicable contract states, signatures, or interpretable physical consequences | Does not compare generation strategies or establish a general mechanism safety ranking |
| Phase VI: live backends and fixed-budget comparison | Sections 4 and 7; bounded RQ2/RQ3 evidence | Demonstrate online strategy execution, feedback, and timing-boundary coverage under an equal denominator | Complete only for one moving healthy-setpoint-stall action; it does not establish general strategy superiority |

Phases I--V close the paper's Motivation Study. Phase VI establishes the first
executable Section 7 slice. A broader route/action corpus plus
confirmation/clustering and ablation remains necessary before the Main
Evaluation or the full state-aware method claim can be called complete.

## Phase I: freeze a physical-execution audit before changing runtime behavior — COMPLETE

The read-only, digest-bound post-hoc analysis covers all 151 frozen admissible
traces. It:

1. list the 12 non-airborne attempts, their cell, maximum achieved height,
   overall result, and affected clauses;
2. retain the original 151-attempt denominator and report the 139 airborne
   and 12 non-airborne traces as descriptive strata only;
3. align physical telemetry with transition, freshness, successor, and fault
   windows without modifying a closed trace or evaluation;
4. report continuous position, velocity, attitude, body-rate, exposure, and
   recovery measurements where the existing workload makes them identifiable;
5. distinguish the masked numeric stale-versus-fresh reference difference from
   the physically observable update-starvation response; retained
   attitude/body-rate commands are reported separately.

The repository artifact is a post-hoc study directory containing
an analysis plan, input manifest, machine-readable summary, tests, and final
report. It must not edit either Stage A1 formal study directory.

## Phase II: run two distinct offline triage tracks — COMPLETE

The root-cause and physical-consequence priorities are intentionally
different.

**Route/root-cause track.** All 11 observed installation violations are in the
attitude setpoint path. Nine of them occur in traces that did become airborne,
so the concentration cannot be dismissed as only the physical-precondition
problem. Reconstruct request, activation, command-consumption, controller,
allocator, and actuator-write timing. Classify the signature as an observer
resolution effect, fixture effect, research-contract finding, or source-level
SUT cause. Do not call it a PX4 bug without a qualified reproduction and
public-spec or source-level grounding.

**Physical-consequence track.** Freshness is the primary A2 exposure
hypothesis. Constant position targets make stale and fresh numerical references
identical, but Phase I shows that update starvation itself remains physically
observable: all eight airborne trajectory-stall traces move approximately
2.70--2.85 m during the freshness window. Existing airborne attitude/body-rate
traces provide smaller retained-command drift signatures. Phase II must
separate reference-value masking, update-starvation response, recovery/landing
motion, and causal attribution before selecting the A2 primary hypothesis.

The eight Dynamic External Mode timeouts outside the invalid RTL fixture also
receive a separate infrastructure diagnosis. Seven share the signature that
the C++ mode received its registration reply while the Python requester never
recorded readiness. This is consistent with a one-shot discovery/reply race,
but the exact DDS cause remains unproven until reproduced.

The frozen triage is recorded in
[`experiments/posthoc_finding_consequence_triage_v1/`](../experiments/posthoc_finding_consequence_triage_v1/).
It localizes all 11 attitude installation signatures to the
activation-to-command-consumption segment: observed complete installation is
401.749--785.004 ms, while activation itself appears in 13.459--28.866 ms.
Nine of these traces are airborne. All 11 remain beyond 300 ms after subtracting
one 100 ms observation period and the registered clock uncertainty, but the
source-level cause remains unresolved pending the high-rate qualification.

The same triage separates 41 airborne freshness-exposure windows and selects
the Stage A2 primary hypothesis: time-varying position-only straight
translation with `SETPOINT_STALL_HEALTHY`, measuring motion-relative tracking
lag and recovery. It also confirms seven
`CPP_REGISTERED_REQUESTER_MISSED_READINESS` timeouts and one distinct
post-registration timeout. The generated results and manifests reproduce
byte-for-byte from an empty output directory.

## Phase III: qualify physical validity, Dynamic readiness, and observer sensitivity — COMPLETE

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

The qualification is frozen in
[`experiments/stage_a2_runtime_qualification_v1/`](../experiments/stage_a2_runtime_qualification_v1/).
All three matched observer tasks were runtime-accepted and satisfied the
sustained physical-takeoff predicate. Their stable real-time-factor medians
were 0.999888--0.999939. The selected `transition` profile retained 7,751
Route observations without a sequence gap or dropout; compared with the
10 Hz baseline, its ULog grew by 443,055 bytes (9.01%), below the frozen 15%
bound. The observer-off image correctly yields no Route evidence and therefore
cannot run the Route Oracles.

Both repaired Dynamic qualification attempts loaded the explicit registration
handoff and were accepted under the three-attempt batch, alongside the
Legacy Offboard control. This qualifies the handshake for A2 execution but is not a
population-level failure-rate estimate. These attempts remain non-formal and
change no paper denominator.

## Phase IV: freeze an A2-specific plan and environment — COMPLETE

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

The independent plan, qualification record, exact matrix, and attestation are
frozen in
[`experiments/motivation_stage_a2_thor_v1/`](../experiments/motivation_stage_a2_thor_v1/).
Plan schema 1.3 adds workload and physical-validity bindings while schema 1.2
remains valid for the frozen A1 plans. The A2 matrix binds the position-only
straight-line profile, selected transition observer, physical-analysis plan,
separate method and safety configurations, paired seeds, four-slot resources,
image `sha256:e9f913...16f3d`, and repository revision `b10b475...34e6`.

Three qualification rounds are retained outside the formal ledger. They first
identified a landing-sensitive provisional safety bound, then an incorrect
Legacy Offboard motion-clock anchor; neither issue was hidden by relaxing the
physical contract. In the final exact-image four-arm probe, all arms were
runtime-accepted, entered motion at 0.752--0.768 m, recorded at least 2.501 m
coverage, and completed terminal cleanup. Formal execution is therefore
authorized only under the frozen matrix.

## Phase V: execute the minimal matched Stage A2 — COMPLETE

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

The official A2 workload uses the same workload and public-action contract in
both mechanisms. Its mechanism-specific runtime remains the executable
baseline. Phase VI subsequently added the generic
decision/schedule/action/request/effect layer under a separate qualification,
identity, preregistration, ledger, and denominator.

The frozen primary execution closed at 51 launches but could not reach three
cell targets because 31 traces hit a command-subject clock-closure defect; it
remains permanently `MEASUREMENT_INSUFFICIENT`. A separately preregistered
remediation changed only that evidence closure rule and the public
takeoff-before-transition fixture obligation, then used a new image,
environment, seeds, ledger, and denominator.

The remediation closed 26/26 formal launches as `ACCEPTED` and
`ADMISSIBLE`: normal Legacy Offboard and Dynamic External Mode both reached
5/5 overall PASS, while both healthy-stall cells reached 8/8 overall VIOLATION.
All 16 violations are the deliberately exercised freshness clause; all
applicable route and successor clauses pass. Thirteen same-seed mechanism
pairs are complete and agree on Oracle status.

The moving task makes the physical effect identifiable without manufacturing
a flyaway. Normal traces end at median x=3.575 m for Legacy Offboard and
3.581 m for Dynamic External Mode. Healthy-stall traces freeze the position
reference at 3.0 m and end at median x=3.041 m and 3.028 m, leaving median
shortfalls of 0.459 m and 0.472 m relative to the complete 3.5 m profile. They
travel a median 1.033 m and 1.012 m after the scheduled stall boundary before
stabilizing at that retained target. The paired differences are small and no
mechanism-superiority threshold was registered.

The result therefore adds bounded physical interpretability, but no new
violation class and no general PX4 defect claim. The complete record is in
[`experiments/motivation_stage_a2_thor_remediation_v1/`](../experiments/motivation_stage_a2_thor_remediation_v1/).

## Phase VI: qualify live strategies and run a fixed-budget comparison — COMPLETE WITH BOUNDED CLAIMS

Phase VI implements one shared live backend for `setpoint_stall`. Every
strategy decision contains the candidate set, seed, planned offset, required
live state, and prior boundary coverage. A separate executor waits for both
observed route activation and motion entry, then writes one owned-process stall
request. The workload records the resulting fault; the raw manifest and formal
closure bind the execution evidence and compact decision.

Six non-formal qualification flights crossed both mechanisms and all three
strategies. All 6/6 were accepted, admissible, and physically valid; absolute
request error was 2.924--14.650 ms. These flights do not enter a formal
denominator.

The separately preregistered formal study
[`experiments/main_strategy_comparison_thor_v1/`](../experiments/main_strategy_comparison_thor_v1/)
closed exactly 18/18 launches as accepted, admissible, and physically valid.
Its append-only ledger has 54 events and chain head
`82edada94d9ae99b0b13af2e90487c2a7eb1e8aeb7a06f871f04dd2c4cc36499`.
All attempts produced one state-conditioned action request and one admissible
freshness violation.

Under three launches per mechanism-strategy cell, official sequence covered
only the fixed `boundary` timing bin. Bounded random timing covered
`pre_boundary`, `post_boundary`, and `late`; state-aware covered
`pre_boundary`, `boundary`, and `post_boundary`. The state-aware second and
third decisions consumed prior live coverage and selected uncovered bins, so
the feedback loop is executable. Random and state-aware nevertheless tie at
three observed bins, all strategies reach the same freshness signature on the
first launch, and all evaluate the same 16 applicable clauses. The evidence
therefore supports live-backend correctness and greater timing coverage than
the fixed sequence in this sample, but no ranking between random and
state-aware and no general search-effectiveness claim.

## Achieved end state of this work package

### Repository state

With Phases I--VI complete, the repository contains:

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
- a shared state-conditioned live executor, deterministic replayable decisions,
  feedback-bound state-aware selection, and fail-closed strategy validation;
- a qualified and separately preregistered 18-launch strategy-comparison
  study with an exact matrix, attestation, 54-event ledger, compact evidence,
  per-attempt analysis, reproducible summary, and bounded final report;
- a clean worktree and a complete repository-validation pass.

### Narrative and paper state

The narrative and paper state at this milestone is:

```text
Stage A1: COMPLETE WITH BOUNDED CLAIMS; frozen and unchanged
Stage A2: COMPLETE under its own preregistration, identity, ledger, and denominator
Paper Section 6 Motivation Study: COMPLETE
Paper Section 7 Main Evaluation: PARTIALLY COMPLETE; one-action vertical slice complete
Gate 4b moving-workload realism bridge: PASS WITH BOUNDED CLAIMS, retaining a null result if observed
Gate 5: PASS; Gate 6: PASS for the owned setpoint-stall backend
Gate 7: PASS WITH BOUNDED CLAIMS for the 18-launch vertical slice
Gate 8 and full route-corpus C6/C7 claims: still PENDING
```

Stage A2 completion depended on admissible execution and honest reporting, not
on obtaining a positive result. A null result must be retained if movement
adds no new signature or measurable consequence. If it does add evidence, the
allowable claim is bounded to the locked Thor SITL mission and may state that
motion context changed contract applicability, violation signatures, or
physical exposure. It may not claim real-flight danger, a general PX4 defect
rate, universal mechanism superiority, or state-aware search effectiveness.

The next work package expands Section 7 beyond this single action. It must
freeze a representative route/action corpus, retain equal budgets and shared
seeds, add confirmation and ablation sufficient to distinguish feedback value
from random timing, and cluster/minimize independent findings. Until that work
is complete, the paper may report the Phase VI implementation and bounded
coverage result but must not claim overall state-aware superiority or complete
C6/C7.

For a beginner-oriented explanation of the repository narrative, the concrete
Stage A1 flight workloads, Runtime Route Instance, and a complete transition,
see [REPOSITORY_UNDERSTANDING_GUIDE.md](REPOSITORY_UNDERSTANDING_GUIDE.md).
