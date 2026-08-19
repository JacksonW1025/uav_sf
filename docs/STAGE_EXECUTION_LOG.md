# Stage execution log

## What this file is

A running record of how the [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md) stages are
being executed, step by step. It exists so work can be resumed by someone — or
some session — that has no memory of the previous steps.

It records intent, position and decisions. It is not evidence. Closed reports,
ledgers and attestations remain authoritative for their own identities, and
[CURRENT_STATUS.md](CURRENT_STATUS.md) remains the record of completed
implementation and evidence.

**Update rule:** this file is updated in the same commit as the work it
describes. A step is marked complete only when its artifacts exist and the
repository validation passes. A step that is partly done says which part.

## How to resume

1. Read the step ledger below and find the first step that is not complete.
2. Read its acceptance criteria and the artifacts of the step before it.
3. Check the standing decisions and invariants, which constrain how the work is
   allowed to proceed.
4. Do that step, update this file, run `./scripts/validation/validate_repo.sh`,
   and commit both together.

## Position

```text
v8 plan stage:      Stage 2, construct the core action and workload corpus
Stage 1:            complete, exit checks met
Corpus freeze:      proposed and conditional, deliberately not signed
Current step:       Step C-adjacent, port the adjacent Land request
Formal campaigns:   none authorized, none running
```

## Standing decisions

Taken in the [conditional freeze](../experiments/stage2_core_corpus_freeze_v1/CONDITIONAL_FREEZE.md),
which carries the full reasoning:

1. The proposed core corpus is seven actions: six that already exist as
   fixtures with retained evidence, plus `restart_producer_after_loss`, whose
   legality depends on the outcome of an earlier action.
2. Two compared mechanisms, `legacy_offboard` and `dynamic_external_mode`. The
   action grammar is made orthogonal where the system permits; the two
   registration-protocol actions are inherently dynamic-only. `mode_executor`
   leaves the main comparison.
3. Baselines are deferred. Two invariants are kept so deferring costs nothing:
   timing stays five discrete bins, and the corpus stays near seven actions, so
   the single-action layer stays enumerable and the sequence layer does not.

Workload frozen for the main comparison: the `straight_line` moving profile,
trajectory setpoints only.

## Step ledger

### Step A — write the core actions as checkable predicates — COMPLETE

Goal: express each proposed action as a precondition over the semantic state,
and validate those predicates against evidence instead of asserting them.

Acceptance: every retained firing of a proposed action satisfies its
precondition on the state immediately before it fired, or the mismatch is
explained and fixed.

Artifacts: [scripts/corpus/core_actions.py](../scripts/corpus/core_actions.py),
[scripts/corpus/precondition_check.py](../scripts/corpus/precondition_check.py),
[experiments/stage2_core_corpus_freeze_v1/](../experiments/stage2_core_corpus_freeze_v1/FINAL_REPORT.md).

Result: 213 attempts checked. Six predicates consistent with every retained
firing; `restart_producer_after_loss` reported unvalidated because it has no
implementation. Two model defects found and fixed — a derived `re_entry` phase
is not evidence of a re-entry action, and one action can be recorded by two
observers, which is now separated by activation identity.

### Step B — make the action selectable — COMPLETE

Goal: the policy chooses which action to apply and when, instead of choosing
only when to apply an action fixed by the matrix cell.

Acceptance:
- a decision selects an (action, timing) pair from the declared corpus;
- the decision stays a pure function of its inputs, so the container re-derives
  and compares it;
- an action that no live backend can apply for the mechanism is never offered;
- the executor refuses to apply an action whose live markers it cannot observe;
- retained schema 1.0 decisions still validate unchanged;
- a non-formal qualification shows the same seed producing the same schedule,
  an illegal action being refused, and the applied schedule being recorded.

Done: decision schema 2.0 in
[live_strategy_backend.py](../scripts/runtime/live_strategy_backend.py) selects
over the joint action and timing space, with action and timing drawn from
independent sub-seeds so one seed explores the space rather than a correlated
slice. `enabled_corpus_candidates` offers only wired, mechanism-available
actions. The executor in
[strategy_action_executor.py](../scripts/runtime/strategy_action_executor.py)
resolves each action's declared live markers and fails closed on any marker it
cannot observe. Schema 1.0 is untouched and still validates, so retained
evidence stays reproducible. Covered by
[tests/test_corpus_decision.py](../tests/test_corpus_decision.py).

Live: the qualification passed. The image `uav-sf-family-a-thor:step-b-2c6b754`
was built and attested, and 18 attempts across two mechanisms and three
strategies were all accepted, admissible, physically valid and action-contract
complete, with all six units passing and the state-aware feedback check passing
for both mechanisms. The policies applied the stall 13 times and the producer
termination 5 times over 5 distinct (action, timing) units, so the action was
chosen rather than configured. No formal ledger was opened.
See [the qualification record](../experiments/step_b_corpus_selection_qualification_v1/QUALIFICATION_ATTEMPT.md)
and [its result](../experiments/step_b_corpus_selection_qualification_v1/qualification.result.json).

Running it found five defects that no host-side test could reach: the decision
never reached the container in corpus mode; the `run_sitl` guard compared a core
action identity against a runtime fault mode; the workload applied the fault
mode it was launched with, so a policy could name one action while the flight
performed another; the in-flight executor read the single-action coverage key;
and the batch summary read those keys and aborted on one rejected attempt. All
are fixed, and each wired action now carries a live profile that fixes its
runtime fault mode and contract obligations.

Two environment findings are recorded rather than tuned away. Machine quiet time
is a precondition: an earlier batch had every attempt rejected for clock
uncertainty because an unpinned desktop process took about two cores from the
pinned CPU sets, dropping the central real-time factor to 0.563 against 0.999.
And the clock fit still flakes at roughly one attempt in 36 even on a quiet
machine, so a gate demanding 18 of 18 will occasionally fail for reasons
unrelated to what it tests. Decide about that before a fixed-budget campaign.

A plan error was corrected: a dynamic external mode producer loss installs
internal RTL, not Land, so the spec now declares the fallback per mechanism. The
successor a workload requests after a completion and the fallback the system
installs after a fault are different obligations.

### Step C — close the availability gaps — IN PROGRESS

Goal: make the grammar orthogonal and add the one new action.

Acceptance: each ported or new action has a non-formal qualification recording
that its precondition gates execution, its applied schedule is recorded, and its
cleanup holds; the precondition replay from Step A still reports every action
consistent and none unvalidated.

#### C-anchor — give each action its own timing anchor — COMPLETE

Planning the three ports exposed a shared blocker. Timing offsets were anchored
to route activation for every action, but the three remaining actions do not
share that clock: a re-entry is interesting relative to the successor taking
over, and an adjacent request relative to the completion boundary. Anchoring
them to activation would have kept the code working while silently removing the
distinction each action exists to test — the adjacent request's before, near and
after buckets would all have collapsed to before.

The live profile now carries a `timing_anchor`, which must be one of the
action's own live markers and must be observable in flight. The executor
resolves the anchor from the decision and measures the applied offset from it.
`successor_installed` became an observable marker, sourced from the
`successor_observed_active` record both workload nodes already emit. The two
wired actions keep `route_active`, so their behaviour is unchanged.

This changed the decision schema, so the next live batch needs a rebuilt image.

#### C-reentry — make re-entry selectable on both mechanisms — COMPLETE

The dynamic requester now has a repeat-cycle loop, both nodes take a
`scheduled_action` parameter and wait for the executor's request when the policy
selected re-entry, and the action anchors on `successor_installed`. The
qualification passed 18 of 18 on the first batch, with all three actions
selected and applied across both mechanisms over 8 distinct units and the
state-aware cells visiting every action. A re-entry attempt enters the tested
route twice in one episode, separated by route epoch and activation identity.
See [the qualification record](../experiments/step_c_reentry_qualification_v1/QUALIFICATION.md).

A latent defect surfaced here: an unset action-request path was passed as an
empty ROS parameter override, which the parameter parser rejects, so any run
without a strategy decision would have failed at node startup.

#### C-restart — implement the reclaim — COMPLETE

The reclaim was implemented, found unreachable, and then made reachable by
correcting the measurement rather than the system.

The first attempt failed on every reclaim: the runner learned of the producer
loss by polling the process, about eleven seconds after telemetry already showed
the installed safe route, by which time the aircraft had landed. The loss is now
derived from telemetry, and the reclaim starts from the main loop instead of the
branch that waits for that notice. The tested failsafe configuration is
unchanged.

Two further defects appeared once it executed. Its plan required a completely
installed fallback that the action exists to preempt, which is a
self-contradictory obligation, so it no longer expects one. And its timing bins
were 3.5 to 6.5 s after the anchor while the window closes on touchdown, so the
supervisor stopped those attempts on ground contact; timing bins now belong to
the action, still five ordered discrete values, with the reclaim's spanning 0.5
to 2.5 s.

The qualification then passed 18 of 18 with four selectable actions over seven
distinct units. A reclaim episode completes, loses its producer, has the safe
route installed and revoked, and reclaims the tested route under a new producer
session and route epoch.
See [the record](../experiments/step_c_restart_qualification_v1/REACHABILITY_FINDING.md).

#### C-adjacent — port the adjacent Land request — NOT STARTED

Work: launch the manual requester for both compared mechanisms and anchor it on
the completion boundary through the C0 mechanism.

### Step D — wire the registration and health actions — NOT STARTED

Goal: make `withhold_health_reply` and `exhaust_registration_capacity`
selectable rather than cell-configured. Both are dynamic-only by nature of the
system under test. Both need live markers the executor can observe, which do not
exist yet.

### Step E — sign the corpus freeze — NOT STARTED

Goal: satisfy the five signing conditions in the conditional freeze and record
the signed corpus with each action's qualification attached.

### Step F — Stage 3 closed loop — NOT STARTED

Goal: move selection in-flight. The executor observes, filters admissible
actions against derived live state, applies one, re-observes, and selects again,
so an episode can carry a state-dependent sequence rather than one action.

Baselines — systematic enumeration and state-conditioned feedback-free
generation — remain deferred by standing decision 3.

## Invariants

- Non-formal qualification never enters a formal ledger or denominator.
- A new action, route, workload or strategy requires qualification,
  preregistration, a new identity and a separate denominator.
- Decision schema 1.0 stays reachable and unchanged so retained studies remain
  reproducible; new behaviour goes into a new schema version.
- A derived state phase describes what the system did. It is never evidence
  that the tester performed an action.
- Timing stays five discrete bins; the corpus stays near seven actions.
- Closed studies, their thresholds and their reports are never edited.

## Next concrete action

C-adjacent is the last availability gap: launch the manual requester for both
compared mechanisms and anchor it on the completion boundary through the
per-action anchor and bins. It is the one core action still implemented only for
the mode executor.

After that, Step D wires the registration and health actions, which are
dynamic-only by nature of the system under test and need live markers the
executor cannot observe yet. Then the corpus freeze can be signed.

Four actions are qualified and selectable today: the owned stall, the producer
termination, route re-entry, and the producer reclaim.

Before any live batch, confirm no unpinned process competes for the pinned CPU
sets, and afterwards confirm the central real-time factor is near 1.0.
