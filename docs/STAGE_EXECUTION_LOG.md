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
v8 plan stage:      Stage 3, close the selection loop
Stage 1:            complete, exit checks met
Corpus freeze:      signed, seven actions, unchanged by this step
Current step:       Step F; host side complete, batch flown 15/18
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

Why this stays open with all four parts complete: the first clause is met for
every ported and new action, and nothing is unvalidated any more. The second is
not. Step E left two instances inconsistent, both in one reclaim episode and
both naming one fact — the producer-loss fault reaches the trace later than
either the executor or the failsafe knew about it. Step F measured that latency
from the other side and found the same thing, so the residue is a property of
when the fault becomes recordable, not an unfinished port. Closing this step
means either widening the two predicates, which would hide it, or recording the
divergence as the accepted reading. That decision has not been taken.

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

#### C-adjacent — port the adjacent Land request — COMPLETE

The request is a public Land command, so porting it from the mode executor was
an anchoring change rather than a new stimulus. The qualification passed 18 of
18 with five selectable actions, and the request lands where it was aimed: +4 ms
from the completion for the boundary bin and +270 ms for the next one, against a
250 ms bin spacing.

Two timing defects were found by measuring the request against the completion,
and both would have passed a qualification that only asked whether the action
executed. Starting the requester on demand cost 600 ms, wider than the spacing
between the bins it exists to distinguish, so it now starts with the workload
and fires on a trigger. And the bins were anchored on motion entry, which is
progress-based, so every bin landed about three seconds late; both producers
measure their active period from route activation, so that is now the anchor.

A fixture change was drafted on a misreading — that the two mechanisms anchored
their completions differently — and reverted before it was flown. They do not:
the offboard producer sets its motion start on the first tick after activation.
See [the record](../experiments/step_c_adjacent_qualification_v1/QUALIFICATION.md).

### Step D — wire the registration and health actions — COMPLETE

Both are dynamic-only by nature of the system under test, and both needed a
decision before code.

**Registration capacity** times only the registration that must be refused. The
first design started all eight components on the policy's request, which spanned
the whole active period and broke the moving profile twice. The seven legal slots
are now filled during setup.

**The health withhold is a launch configuration**, not a runtime action: it must
be in effect before the activation it refuses is requested, so it has no moment
to choose and nothing to request. A live profile now declares how an action
reaches the aircraft; a launch configuration carries no bins, waits on no
marker, and is applied and recorded by the runner.

Flying it exposed four contract assumptions that had encoded "every episode
moves" — the injection phase, the progress thresholds, the tested request kind,
and the fault-after-motion ordering. Each reported a violation for something the
episode never claimed to do. All four now represent a workload without motion,
with the strict obligations still applying by default, so every earlier plan
stays valid.

The full seven-action qualification then passed 18 of 18 across both mechanisms,
with both launch-configuration attempts accepted and physically valid.
See [the record](../experiments/step_d_full_corpus_qualification_v1/QUALIFICATION.md).

### Step E — sign the corpus freeze — COMPLETE

The replay a signed corpus must carry was re-run over the whole current evidence
base: 303 attempts, 213 formal and 90 from this stage's qualifications. The
qualification evidence was brought in because the four actions added after Step A
have no instances in the formal corpus.

Nothing is unvalidated any more — the reclaim's marker was still the placeholder
from before it existed, and now recognises a return to an external route after a
producer loss. Five of seven predicates are consistent across every instance.

Two are not, both in the same reclaim episode and both from one cause: a
precondition is evaluated here against the state at the moment an effect appears
in the trace, while the live executor evaluates it against the state at the
moment it decides. Those differ by the revocation latency, which is negligible
everywhere else. The producer loss is recorded after the failsafe already
revoked the external route, and the reclaim request while the vehicle sits in
the internal navigator rather than a named safe route.

The choice is between evaluating against the decision moment, widening two
predicates to the recorded moment, or signing with the divergence noted. It is a
modelling decision, not a defect.

The first was chosen and tried. Judging everything at the decision moment
resolved neither inconsistency and introduced two more, because a launch
configuration has no such moment — its record is written during setup. The split
rule was then implemented instead: a timed action is judged at its decision
moment, a launch configuration at its effect. The health withhold returned to
consistent, and the reclaim predicate was corrected in one narrow way, since
after a loss the vehicle may sit under the internal navigator rather than a
named safe route.

Two instances remain, both in the same reclaim episode, and they now name one
fact: the producer-loss fault reaches the trace later than either the executor
or the failsafe knew about it. The reclaim fails only on the fault clause, at a
moment where the authority it needs is already in place; the producer
termination has no decision moment in that attempt and is judged at the runner's
late record. Widening either predicate further would hide that rather than
resolve it.
See [the blocked-signing record](../experiments/stage2_signed_corpus_v1/SIGNED_CORPUS.md).

Every other signing condition is met.

### Step F — Stage 3 closed loop — IN PROGRESS

Goal: move selection in-flight. The executor observes, filters admissible
actions against derived live state, applies one, re-observes, and selects again,
so an episode can carry a state-dependent sequence rather than one action.

Baselines — systematic enumeration and state-conditioned feedback-free
generation — remain deferred by standing decision 3.

#### F-state — derive the live state the filter runs on — COMPLETE

Planning the loop exposed a blocker of the same shape as C-anchor. The corpus
states each action as a precondition over the semantic state, which is folded
from the closed trace: a ULog, sidecar and clock-bridge artifact that only
exists after the flight. An executor choosing its next action mid-flight has
two lifecycle sidecars and a telemetry sidecar and nothing else, and bridged
that gap with a four-marker table that is not the corpus's own predicate and
had never been compared to one. Filtering on it and calling it the derived live
state would have made the closed loop test something other than what was
signed.

[online_state.py](../scripts/state/online_state.py) now folds the in-flight
sidecars into the state an executor can actually derive. It is a proxy, not
evidence: nothing derived there enters the trace, the Gate or an Oracle. It
never claims the command lineage, which is reconstructed from ULog subject
identity and is reported as an explicit unobservable. It does read the declared
navigation mode, which the route model refuses as evidence of route identity,
and that is why its divergence is measured rather than assumed to be zero.

Each of the six runtime actions declares an `online_gate` beside its offline
precondition. A launch configuration declares none, because it is in effect
before the episode observes anything and gating it would invent a decision
moment it does not have. Every gate drops at least the lineage conjunct, so
every gate is a weakening, and
[online_state_check.py](../scripts/corpus/online_state_check.py) measures the
interval where a gate held while its precondition did not.

Result over 320 accepted attempts, none skipped — the five retained formal
studies plus the five Step B to Step E qualification batches, which hold the
only instances of the four actions added after Step A. No gate would have
blocked a firing its precondition admitted: of 102 observed firings, 101 were
permitted. Every gate is weaker than its precondition somewhere, with one
named cause — in flight, held authority means the vehicle is flying under a
route telemetry reports, while offline it means commands demonstrably reached
the actuators. The gates track the preconditions to within tens of milliseconds
in the moving profile the main comparison uses; the multi-second tails are in
episodes that never activate the tested route and in mode executor cells
outside that comparison.

Two defects were found by measuring, neither reachable by a host-side test.
Telemetry reports a navigation state while the vehicle is still on the ground,
so the two gates that ask only for held authority were true before takeoff and
now also require the airborne observation. And a handover the producer asked
for was being read as a fallback, which made a normal completion look like a
producer loss for the rest of the episode — precisely the state the reclaim is
allowed to act in. A fallback is now a safe route taking over that nothing
requested, which dropped the reclaim's windows from 193 attempts to 37 and its
median from 2.023 s to zero.

One measurement was corrected. Counting any refused firing as a gate defect
flagged a reclaim whose offline precondition was false at that moment too, by
5.1 ms. A gate that refuses what the corpus also refuses is agreeing with it,
so the two are now counted separately and each firing record keeps both states.
That instance is the producer-loss latency the signed corpus already carries.

The signed corpus is unchanged: regenerating the action records and setting
aside the one added field reproduces the signed set exactly.
See [the record](../experiments/step_f_online_state_v1/ONLINE_STATE_AGREEMENT.md).

#### F-obligations — obligations for an episode that carries a sequence — COMPLETE

Decision taken before code, as Step D's two actions were. An episode that may
carry several actions cannot preregister one fixed set of obligations, and the
plan field semantics decide what is possible: `fault_expected` is **two-sided**,
so a False plan that observes a fault is a violation, while
`completion_expected` and `fallback_expected` are one-sided and simply stop
being checked. `target_activation_count` is already an interval.

Two consequences. Whether an episode has a fault must be fixed before flight,
which sorts the seven actions into four classes by (fault expected, fault
mode); the process_exit class is exactly `terminate_owning_producer` and
`restart_producer_after_loss`, the pair standing decision 1 names. And an
envelope plan that sets both one-sided obligations to False would switch off
`fallback_installed` and `target_installed` — the contract boundaries those two
actions each aim at, which is the dependent variable of the study.

So the plan declares both sets and the condition that selects between them.
Schema 1.4 adds a `sequence_obligations` block: the transition carries the
obligations that hold when the condition does not, the block carries the ones
that replace them when it does, and
[sequence_obligations.py](../scripts/evaluator/sequence_obligations.py) picks
the branch once, before the Gate, so the Gate and all four Oracles judge one
resolved set. Three rules keep it honest — the condition and both branches are
preregistered, the condition is decided by trace evidence alone and never reads
the executor's own record of what it did, and the evaluation reports which
branch was applied. Schema 1.2 and 1.3 plans resolve to themselves, so every
retained study evaluates exactly as before.

The Gate needed one further decision. A plan preregisters the union of both
branches' required event kinds, so a reader can see what either sequence would
owe, but demanding the union would make every episode inadmissible for lacking
the other sequence's events. The resolution narrows the required kinds to the
branch that ran. Resolving before the Gate is safe: the condition reads trace
events only, and evidence too thin to establish it makes it false, which
selects the branch that demands more.

**A defect was found in the existing reclaim plan and is not fixed here.** The
one retained attempt whose plan declares `target_activation_count` `[2, 2]`,
`step-cr-q-offboard-random-001`, evaluates to VIOLATION on
`route_conformance.reentry_identity`. The clause counts repeated public
requests *from the declared source route*, and a reclaim's request comes from
the internal navigator the failsafe left the vehicle in, not from the source
the plan names. The count and the clause measure different things, so the
reclaim is being given an obligation it does not owe — the same shape as the
self-contradictory fallback obligation C-restart already removed. Repeated-entry
identity is the re-entry action's contract boundary; the reclaim's is
`target_installed`, which the installation clause judges and which passes.

It is recorded rather than fixed because both available fixes are out of scope
for this step: correcting `activation_count` would edit the signed corpus, and
widening the clause would change Oracle behaviour for every study. The
conditional branch therefore leaves `target_activation_count` alone, and the
qualification attempt keeps its VIOLATION, which is accepted evidence rather
than a failed attempt.

Covered by [tests/test_sequence_obligations.py](../tests/test_sequence_obligations.py),
including a check that the two branches are not interchangeable: a reclaim
judged by the terminate-only obligations must not pass, or the conditional plan
would be decoration.

#### F-decide — choose in flight and still re-derive it — COMPLETE

Every earlier decision surface was computed on the host before the flight, so
the container could recompute it and refuse a difference. A decision that
depends on what the flight observed cannot work that way: the host does not
have the inputs.

The invariant is kept by moving what is frozen. The host freezes a *policy* in
[closed_loop_policy.py](../scripts/runtime/closed_loop_policy.py), schema 3.0 —
strategy, seed, episode class and its corpus, timing bins. The flight applies
that policy at each decision point and records the inputs it applied it to.
Re-derivation replays the policy over those recorded inputs and refuses any
step whose choice differs.

That leaves exactly one thing the flight is trusted for, and it is named rather
than hidden: the observed state. A choice cannot be forged, because it is
recomputed. The admissible set is not trusted at all — it is recomputed from
the recorded state rather than read from the record, so a flight cannot widen
its own options. The state itself could be, and is checked separately by
replaying the retained sidecars through the F-state projection.

[episode_classes.py](../scripts/corpus/episode_classes.py) declares what one
launch admits. Grouping the seven core actions by expected fault and fault mode
yields exactly four classes; only `process_exit_reclaim` is declared, because
it is the only one whose second action depends on the outcome of its first. It
carries the baseline obligations and the branch F-obligations resolves between,
and its fallback differs by mechanism.

Three findings came out of building it.

**The first action is not a choice.** The class is launched with its fault mode
installed and its plan declares `fault_expected`, which is two-sided, so an
episode that applied nothing would violate its own plan. Stopping is therefore
offered only once something has been applied, and a first decision point with
nothing admissible fails closed rather than flying an episode that is already a
violation. What follows the first action is the choice.

**Stopping is a unit, not a timeout.** An episode that ended because the policy
chose to stop and one that ended because nothing was admissible are different
outcomes. Making the choice explicit keeps them distinguishable instead of both
looking like an episode that ran out of time.

**Each action scores against its own window.** The single-action decision
compared every bin against one global offset because all five surrounded one
moment. Here they do not: a termination's bins span the active period and a
reclaim's span the ten seconds between the fallback and touchdown. The global
offset left the policy ranking a reclaim's bins by a property they do not have,
and always picking the latest; each action's official timing is now the middle
bin of its own window, and the global offset is gone from the contract.

Measured over 60 seeds: the bounded-random policy reaches all five termination
bins and produces both one-action and two-action episodes, so the sequence
length is chosen rather than fixed by the class. The state-aware policy prefers
an uncovered unit and stops once nothing uncovered is left.
Covered by [tests/test_closed_loop_policy.py](../tests/test_closed_loop_policy.py).

#### F-executor — run the loop in flight — COMPLETE

[closed_loop_executor.py](../scripts/runtime/closed_loop_executor.py) folds the
in-flight sidecars into the online state, asks the policy what to apply next,
applies it at that action's own anchor, and goes back to observing. Four things
it does not do, each for a reason the study depends on: it never widens its own
options, never invents a decision moment, never treats running out of time as a
choice, and never spends CPU it does not have to.

Two of those needed work rather than a comment.

**The fold is incremental.** `derive_online_trajectory` re-reads its whole
input, which is right for a replay and wrong in flight: the telemetry sidecar
reaches thousands of records and re-folding it on every poll would spend real
CPU on the cores the attempt is pinned to. Competing for those cores is exactly
what the clock uncertainty bound measures, so the live fold keeps only the
current state and the first time each marker held, and telemetry is read on its
own slower cadence. `OnlineProjection` and a tail reader that holds a partial
line back replaced the whole-file re-read.

**A decision point is opened by an anchor, not by a clock.** A step is decided
when some unapplied action has both become admissible and had its own anchor
observed, or when the episode reaches a terminal state having applied
something. Deciding on a fixed clock would make the choice depend on the poll
rate rather than on what the flight did, and offering an action whose anchor has
not been seen would let the policy pick a unit the executor could not then
place. Running out of time remains a refusal, never a recorded choice to stop.

Each action is requested on its own path. One shared path was enough while an
episode applied one action; with two, the second would overwrite the first or
the wrong consumer would act on it.

The integration test drives the loop with sidecars appended in stages and then
replays the log it produced against its policy, which is the whole contract in
one check: the flight chose, and the choice re-derives from what it recorded.
Covered by [tests/test_closed_loop_executor.py](../tests/test_closed_loop_executor.py).

#### F-wiring — one launch that admits both sequences — COMPLETE

`run_sitl` takes `--episode-class` and `--strategy-policy-path`, re-derives the
policy for the same reason it re-derives a decision, and refuses a launch whose
fault mode, mechanism or workload profile differs from the class. A class
launch starts the closed-loop executor instead of the single-action one, gives
the producer and the reclaim their own request paths, and triggers the reclaim
from its own request rather than from the producer's.

`qualification_attempt` configures the launch and the plan from the class:
obligations, workload phases and fault mode come from the class, and the plan
is the 1.4 form carrying the baseline plus the branch. `run_container` forwards
the policy and the class, and the qualification driver reads a closed-loop
episode's decision log, requires that it re-derives, and takes each attempt's
fallback obligation from the branch its own trace selected rather than from
what the policy meant to do. Its coverage feedback is the union of the units
earlier episodes applied, because one episode can now apply more than one.

Every single-action path is untouched: with no class named, all of this is
skipped and the 255 earlier tests pass unchanged.
Covered by [tests/test_episode_class_launch.py](../tests/test_episode_class_launch.py).

#### F-live — the non-formal qualification — FLOWN, GATE NOT PASSED

A single smoke flight was flown before any batch, because every earlier step in
this stage found defects live that no host-side test could reach. It found
three, and one of them is a finding about the retained corpus rather than about
this step.

**Cross-source fold order.** The loop read the lifecycle sidecars every 20 ms
and telemetry every 500 ms, sorting within each batch. That is not enough. The
lifecycle `fault_detected` folded first and advanced the state to "fault
observed"; the same telemetry batch then delivered a Loiter reading from before
the activation, and against that already-advanced state it looked like a safe
route taking over unasked. The fallback marker took that older record's
timestamp — two hundred milliseconds *before* the route activation it is
supposed to follow. The reclaim's whole window is measured from that marker, so
all five of its bins collapsed onto "immediately": applied 178 ms after the real
fallback instead of the 1.5 s selected. Records now pass through an intake that
folds across sources in arrival order, with telemetry's latest arrival as the
watermark. Re-flown: 1.5026 s against 1.500 s planned. An offline replay merges
every source at once and sorts, so it could never have reproduced this.

**The successor was declared as a branch obligation.** The producer is launched
to release to one route; the branch named another, so the plan demanded a
release the workload was never configured to make. The successor is a property
of the class.

**The retained single-action reclaim never ran the sequence it names.** This is
the finding. Reading `step-cr-q-offboard-random-001`'s timeline: the producer
completed at 8.045 s, released to its successor at 8.124 s, and only exited at
9.645 s, with the reclaim starting 133 ms later and the runner recording a
`fallback_triggered` for a route that had already been the successor for two
seconds. The producer died holding nothing. Its executor cannot tell a
requested handover from a fallback — Hold is Loiter, so a normal release looks
like a safe route taking over — so it anchored the reclaim after the completion.
That fixture measures re-entry after a completed episode, not reclaim after a
loss.

The closed loop terminates the producer while it owns the route, and everything
the action exists to test follows: the command age climbs from 217 ms to
1049 ms while PX4 consumes the dead producer's last setpoint, the failsafe takes
over, and the reclaim follows. The freshness violation reporting that window is
the `command_stale` boundary being observed, and is accepted evidence rather
than a defect. The retained reclaim shows zero stale commands because nothing
was ever stale in it.

This does not edit any closed report. It is recorded here because it changes how
the retained reclaim evidence should be read, and because Step E's remaining
inconsistency — the producer-loss fault reaching the trace later than either the
executor or the failsafe knew — is the same fixture seen from the other side.

**The batch then flew: 15 of 18, so the gate did not pass.** Nothing failed for
a reason unrelated to what it tests. All eighteen were admissible and physically
valid and the clock fit held in every one, so the flake this stage has been
carrying did not decide anything here. The three failures were
`FORMAL_SAFETY_STOP`, the independent supervisor stopping the aircraft twice for
unexpected ground contact and once for exceeding the vertical speed bound.

What the batch establishes: every decision log re-derived against its frozen
policy without a divergence, in all six units. The bounded-random policy
produced both two-action and one-action episodes in the same cell, so the
sequence length is chosen rather than fixed. Both obligation branches occur in
real evidence — twelve `when_absent` and five `when_observed` — each attempt
judged against the obligations its own trace selected, with neither obligation
switched off to make the other possible. Every timing bin was reached.

**The finding is a mechanism difference at the reclaim.** Offboard installed
the reclaimed route completely in 5 of 6 attempts, about 3.7 s after the
producer restarted. Dynamic did so in **0 of 9**: its reclaim producer is a new
process that must register the external mode again and wait for PX4 to assign a
mode identifier, which took about 11 s, against a 13 to 16 s window spent under
a descending return-to-launch. The three safety stops are the end of that — the
reclaim arriving near the ground under a descending failsafe.

No retained evidence could show this, for the reason above: the single-action
fixture reclaimed under a loiter, and the ten-second window Step C recorded was
measured there.

Three readings are open and none is taken: the difference is the result and
belongs in the mechanism comparison; or the dynamic timing bins need
re-measuring against a descending failsafe; or the reclaim is offboard-only in
practice, which would change a signed availability. They are distinguishable by
measurement.

**Where the delay is, measured from this batch without re-flying.** The reclaim
producer does not re-register; it loads the handoff the first producer left and
spends 2.2 to 3.2 s starting and prestreaming. The whole wait is *after* the
request: dynamic takes 7.6 to 10.8 s from request to activation, offboard takes
0.1 to 0.2 s. The navigation state at the request separates them. Offboard
requests from `AUTO_TAKEOFF` and is granted `OFFBOARD` 0.14 s later at three
metres, so authority is genuinely taken back in flight. Dynamic requests from
`AUTO_LAND` at 3.76 m and is granted nothing; the descent runs to completion,
the aircraft touches down and disarms, and only then does the external mode
activate, on the ground, immediately commanding a takeoff. That is the
unexpected ground contact the supervisor stopped. This makes the second reading
the weakest of the three: moving the request earlier cannot shorten a wait that
begins after the request.

**Two attempts to re-fly the offboard cells alone are void, cause not yet
identified.** Both gave 0 of 9, almost all observability-rejected on clock
uncertainty, with the central real-time factor far under bound. A first
diagnosis blamed analysis run on the host during the batch; the second re-fly
was performed with the host otherwise idle and reproduced the failure, so that
diagnosis was wrong and is withdrawn.

| run | driver | concurrency | central real-time factor | admissible |
| --- | --- | --- | --- | --- |
| full batch | `run_strategy_qualification` | 3 | 0.9989 – 0.9991 | 18 of 18 |
| offboard re-fly, host busy | ad-hoc script | 3 | 0.5629 – 0.8223 | 0 of 9 |
| offboard re-fly, host idle | ad-hoc script | 3 | 0.5772 – 0.8585 | 0 of 9 |
| single attempt, host idle | ad-hoc script | 1 | 0.9991 | 1 of 1 |

The median real-time factor is 0.9998 or better everywhere, so the simulation
runs real-time most of the time; what moves is the central window minimum,
which is sustained stalling. The machine is not the explanation: a single
attempt flown afterwards on the same host and image was accepted with 0.9991
and 4.3 ms of clock uncertainty. Nor is concurrency by itself, because the full
batch also ran three at a time and held 0.999.

What is left is a difference between the ad-hoc offboard script and
`run_strategy_qualification` that has not been found. Their slot assignment,
CPU-set selection, barrier check and `_parallel` calls read the same. Until it
is found, a partial re-fly should go through the real driver rather than a
script written for the occasion, and any result from that script is not
evidence.

The wider point stands regardless: nothing in the tooling notices a real-time
factor collapse until the attempt is rejected after the fact, and the two-phase
barrier only holds back a batch's own analysis.

**The batch was then replicated through the real driver with independent
seeds**, and held 0.9988 to 0.9994 across all eighteen — same host, same image,
same three-at-a-time concurrency as the script that could not. 13 of 18, the
gate again not passed, again only on safety stops.

**The mechanism difference replicated exactly.** Over both batches, 36
attempts:

| mechanism | attempts | reclaim completely installed | not installed | safety stops |
| --- | --- | --- | --- | --- |
| `dynamic_external_mode` | 18 | **0** | 17 | 3 |
| `legacy_offboard` | 18 | **11** | 7 | 5 |

Dynamic reached four of its five reclaim bins and offboard all five, so this is
not a property of which timings were drawn. The dynamic reclaim was requested in
every one of its eighteen episodes and completely installed in none.

The second half of the result is that the offboard reclaim is not reliable
either. It installs in 11 of 18, and when it does not the aircraft is close
enough to the ground that the supervisor stops the attempt — offboard has more
safety stops than dynamic, not fewer. The difference is not that one mechanism
works and the other does not. It is that one sometimes completes the
installation inside the failsafe descent and the other never does.

Every decision log re-derived in all twelve units across both batches.
See [the replication record](../experiments/step_f_closed_loop_replication_v1/REPLICATION.md).
See [the record](../experiments/step_f_closed_loop_qualification_v1/QUALIFICATION.md).

## Invariants

- Non-formal qualification never enters a formal ledger or denominator.
- A new action, route, workload or strategy requires qualification,
  preregistration, a new identity and a separate denominator.
- Decision schema 1.0 stays reachable and unchanged so retained studies remain
  reproducible; new behaviour goes into a new schema version.
- A derived state phase describes what the system did. It is never evidence
  that the tester performed an action.
- The online gate orders the flight and is never the precondition of record.
  The offline replay over the closed trace stays the authority on whether an
  action was legal; a loop that judged itself by its own gate would be marking
  its own work.
- A conditional obligation is decided by trace evidence alone. A tester that
  could assert the condition would be choosing which obligations to be judged
  against, which is the dual of the rule above.
- Timing stays five discrete bins; the corpus stays near seven actions.
- Closed studies, their thresholds and their reports are never edited.
- A fixture that runs is not the same as a fixture that runs what it is named
  after. The single-action reclaim passed every gate for four steps while
  measuring something else.
- A batch is flown with the real driver. A script written for one occasion is
  not evidence until it has reproduced the driver's real-time factor.

## Next concrete action

Decide how to read the reclaim result, using the three options in the F-live
entry. That decision is a research judgement about the mechanism comparison, not
an engineering fix, and it gates whether the bins are re-measured or the corpus
availability changes.

Two of the three readings are now much weaker than when they were written. The
delay is entirely after the request, so moving the request earlier cannot
shorten it; and the difference replicated across independent seeds with four of
five dynamic bins exercised, so it is not a property of the timings drawn. What
also changed is that the offboard reclaim turned out to be unreliable too — 11
of 18 — so the reading is no longer "one mechanism can reclaim and the other
cannot".

Whichever is chosen, the ten-second reclaim window recorded in Step C was
measured under a loiter and does not describe a real failsafe. Re-measuring it
against a descending failsafe is needed before any fixed-budget campaign that
includes the reclaim.

The earlier plan for this section, now done:

F-live, the non-formal qualification. Every host-side part of Step F is
complete and verified by 268 tests: the live state the filter runs on and its
measured cost, obligations that judge a sequence episode without switching off
the boundaries it tests, a policy that chooses in flight and re-derives from
what it recorded, the executor that runs the loop, and the launch that admits
the whole class.

What is left can only be learned by flying it. Every earlier step in this stage
found defects live that no host-side test could reach, and there is no reason
to expect this one to differ.

Before the batch: build and attest a new image, because the decision surface
changed. Confirm no unpinned process competes for the pinned CPU sets — a
desktop session once cost about two cores and had all 18 attempts rejected for
clock uncertainty. Afterwards, confirm the central real-time factor is near 1.0.

The clock fit still flakes at roughly one attempt in 36 on a quiet machine
while the qualification gate requires every attempt to pass it, so this batch
may fail for a reason unrelated to what it tests. That needs a decision before
a fixed-budget campaign; this batch will meet it first.

The corpus it consumes is [signed](../experiments/stage2_signed_corpus_v1/SIGNED_CORPUS.md)
and unchanged: seven actions, six timed and one applied at launch, all
consistent across 230 attempts.

Baselines remain deferred by standing decision 3.

A live batch is not yet needed; F-state required none. Before the first one,
two things are still open. Confirm no unpinned process competes for the pinned
CPU sets, and afterwards confirm the central real-time factor is near 1.0 — a
desktop session once cost about two cores and had all 18 attempts rejected for
clock uncertainty. And the clock fit still flakes at roughly one attempt in 36
on a quiet machine while the qualification gate requires every attempt to pass
it, so that gate will occasionally fail for a reason unrelated to what it
tests. That needs a decision before a fixed-budget campaign, and the batch that
qualifies F-loop will meet it first.
