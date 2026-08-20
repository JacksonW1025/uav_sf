# Step F, first part: what the in-flight state projection costs

Non-formal. Read-only over evidence that already exists. No ledger was opened,
no denominator was created, and no retained artifact was edited.

## Why this exists

Step F moves selection into the flight: the executor observes, filters the
admissible actions against derived live state, applies one, re-observes and
selects again. Planning that exposed a blocker before any of it could be
written.

The signed corpus states each action as a precondition over the semantic state
in [semantic_state.py](../../scripts/state/semantic_state.py). That state is
folded from the closed trace, which is assembled after the flight from the
ULog, the sidecars and the clock bridge. An executor choosing its next action
while the aircraft is flying has none of it. It has two lifecycle sidecars and
a telemetry sidecar, as they are appended.

So an in-flight filter cannot evaluate the corpus predicates. Until now that
gap was bridged by a four-marker table inside the executor, which is not the
corpus's own predicate and was never compared to one. Filtering on it and
calling the result "the derived live state" would have made the closed loop
test something other than what was signed.

## What was built

[online_state.py](../../scripts/state/online_state.py) folds the in-flight
sidecars into the state an executor can actually derive, under three rules:

* It is a proxy, not evidence. Nothing derived there enters the trace, the
  evidence Gate or an Oracle. The closed trace remains the sole account of what
  the system did.
* It never claims an unobservable field. The command lineage is reconstructed
  from ULog subject identity, so in flight it is reported as `unobservable`
  rather than assumed complete.
* The vehicle's declared navigation mode is an input, which the route model
  refuses as evidence of route identity. That is exactly why the projection is
  a proxy whose divergence is measured rather than assumed to be zero.

Each of the six runtime core actions now declares an `online_gate` beside its
offline precondition. A launch configuration declares none: it is in effect
before the episode observes anything, so gating it would invent a decision
moment it does not have.

Because every gate drops at least the lineage conjunct, every gate is a
weakening: it can hold where the precondition does not.
[online_state_check.py](../../scripts/corpus/online_state_check.py) measures
where and for how long.

## What was measured

Both projections were folded from the same retained attempt and compared over
the interval both observed. 320 accepted attempts, none skipped: the five
retained formal studies plus the five Step B to Step E qualification batches,
which is where the four actions added after Step A have their only instances.

Two numbers matter per action. The **online-only window** is the time the gate
held while the precondition did not, which is where a closed loop would act on
a state the corpus does not admit. A **blocked firing** is an action that
demonstrably fired while its gate was false, which would have stopped a flight.

| action | attempts with a window | median | p90 | widest |
| --- | --- | --- | --- | --- |
| `stop_owned_setpoint_stream` | 153/320 | 0 ms | 205 ms | 736 ms |
| `terminate_owning_producer` | 153/320 | 0 ms | 205 ms | 736 ms |
| `adjacent_land_request` | 320/320 | 48 ms | 572 ms | 5.081 s |
| `exhaust_registration_capacity` | 320/320 | 48 ms | 572 ms | 5.081 s |
| `re_enter_route_after_successor` | 187/320 | 7.5 ms | 203 ms | 6.069 s |
| `restart_producer_after_loss` | 37/320 | 0 ms | 7 ms | 12.232 s |

No gate would have blocked a firing its precondition admitted. 102 firings
were observed across the six actions; 101 were permitted, and the one that was
not is the divergence the signed corpus already records, discussed below.

The windows have one cause, and it is the one the projection names: in flight
"some route holds authority" means the vehicle is flying under a route
telemetry reports, while offline it means commands demonstrably reached the
actuators. The two come apart hardest where they should — the multi-second
tails are in episodes that never activate the tested route, and in mode
executor cells outside the main comparison. In the moving profile the main
comparison uses, the gates track the preconditions to within tens of
milliseconds.

## Two defects the measurement found

Both would have shipped into the closed loop, and neither was reachable by a
host-side test.

**Telemetry reports a navigation state while the vehicle is still on the
ground.** The two gates that ask only for held authority were true before
takeoff. They now also require the airborne observation, which the land
detector provides.

**A handover the producer asked for was being read as a fallback.** A safe
route taking over is a fallback only when nothing requested it; when the
producer released to its preregistered successor, the projection recorded a
fallback anyway. That made a normal completion look like a producer loss for
the rest of the episode, which is precisely the state the reclaim is allowed to
act in. Correcting it dropped the reclaim's windows from 193 attempts to 37 and
its median from 2.023 s to zero.

## One measurement correction the evidence forced

The first cut counted any firing the gate would have refused as a defect in the
gate. One reclaim firing came back refused, in
`step-cr-q-offboard-random-001`. Its offline precondition was false at that
moment too, by 5.1 ms: the semantic state there reads `fault=none`, because the
producer-loss fault had not yet reached the trace.

A gate that refuses what the corpus also refuses is agreeing with the corpus,
not defeating it. That instance is the producer-loss latency the signed corpus
already carries, restated in the in-flight projection. The two are now counted
separately, and each firing record keeps both the online state and the semantic
state so the cause is named rather than inferred.

## What this settles for the rest of Step F

The online gate orders the flight. It is never the precondition of record: the
offline replay over the closed trace stays the authority on whether an action
was legal, exactly as a derived state phase is never evidence that the tester
performed an action. A closed loop that treated its own gate as the
precondition would be marking its own work.

## Effect on the signed corpus

None. Regenerating the action records and setting aside the one added key
reproduces
[the signed set](../stage2_signed_corpus_v1/SIGNED_CORPUS.md) exactly: no
precondition, marker, cleanup obligation, live profile or timing bin changed.
The record gained a field describing the in-flight gate, which the signing did
not cover.

## Artifacts

* `online-state-agreement.json` — per-action agreement summary.
* `per-attempt.jsonl` — one record per attempt per action, with the window, the
  first true moment on each side, and both states at any firing.

Reproduce with:

```bash
python3 -m scripts.corpus.online_state_check --root . --output-root <fresh dir> \
  --qualification-study step-b-corpus-selection-qualification-v1 \
  --qualification-study step-c-reentry-qualification-v1 \
  --qualification-study step-c-restart-qualification-v1 \
  --qualification-study step-c-adjacent-qualification-v1 \
  --qualification-study step-d-full-corpus-qualification-v1 \
  --qualification-study step-e-signed-corpus-qualification-v1
```
