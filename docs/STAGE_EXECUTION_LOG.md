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
Current step:       Step B, complete on the host side, live qualification pending
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

### Step B — make the action selectable — HOST SIDE COMPLETE, LIVE QUALIFICATION PENDING

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

Not done: the live qualification. It needs a candidate container image built at
this revision — the project layer rebuilds project code and the ROS workspace on
top of an attested upstream image — plus a qualification spec and a
non-formal environment attestation. No image has been built and no flight has
been run for this revision.

### Step C — close the availability gaps — NOT STARTED

Goal: make the grammar orthogonal and add the one new action.

Work: port the adjacent Land request to both compared mechanisms (an anchoring
change, since the request is already a public command); add a repeat-cycle loop
to the dynamic requester so re-entry works there; implement
`restart_producer_after_loss` on top of the existing producer-exit fixture.

Acceptance: each ported or new action has a non-formal qualification recording
that its precondition gates execution, its applied schedule is recorded, and its
cleanup holds; the precondition replay from Step A still reports every action
consistent and none unvalidated.

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

Run the Step B live qualification. It needs, in order: a candidate image built
from this revision, a non-formal environment attestation for it, a qualification
spec covering both mechanisms and all three strategies, and a run through
`scripts.runtime.run_strategy_qualification`. Until that exists, Step B stays
host-side only and no claim about live action selection may be made.
