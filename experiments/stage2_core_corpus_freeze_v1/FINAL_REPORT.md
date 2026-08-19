# Stage 2 Core Action Precondition Check v1

## Scope and paper role

The proposed core action set is written as predicates over the derived semantic
state, and every predicate is replayed against the retained corpus: 213 accepted
attempts across the five closed studies. It belongs to the paper's
Implementation and Evaluation-setup sections.

The question is narrow and mechanical. For every moment where a proposed action
demonstrably fired in a flight that already happened and was admissible, did its
precondition hold on the state that existed immediately before it fired? A false
precondition there is a defect in the model, never in the flight.

The check is read-only. It adds no launch, no denominator, and no claim about
PX4 behaviour. The selection it validates is recorded in
[CONDITIONAL_FREEZE.md](CONDITIONAL_FREEZE.md) and is deliberately not signed.

## Result

| Action | Status | Actions observed | Duplicate observations | Precondition held |
| --- | --- | ---: | ---: | ---: |
| `stop_owned_setpoint_stream` | consistent | 72 | 0 | 72 / 72 |
| `terminate_owning_producer` | consistent | 16 | 8 | 16 / 16 |
| `adjacent_land_request` | consistent | 30 | 0 | 30 / 30 |
| `re_enter_route_after_successor` | consistent | 20 | 0 | 20 / 20 |
| `withhold_health_reply` | consistent | 8 | 0 | 8 / 8 |
| `exhaust_registration_capacity` | consistent | 8 | 8 | 8 / 8 |
| `restart_producer_after_loss` | unvalidated | 0 | 0 | — |

Six of the seven predicates are consistent with every retained firing.
`restart_producer_after_loss` is reported as unvalidated rather than as passing:
the action does not exist yet, so no evidence exercises its predicate. It stays
unvalidated until its qualification produces flights.

## Two model defects this check found

Both were defects in how the model reads evidence. Neither changes a flight, a
verdict, or a denominator.

### The derived re-entry phase is not evidence of a re-entry action

The first predicate for `re_enter_route_after_successor` recognised the action by
the derived lifecycle phase becoming `re_entry`. Ten firings then failed their
precondition, all in mode-executor cells.

Inspecting one showed the phase was right and the marker was wrong. In
`timing-executor-before-remediation-001` the vehicle really does enter
`mode_executor` twice: once at `px4-epoch-2` during component startup, and again
at `px4-epoch-4` for the tested transition. Both entries reach complete lineage.
So the system did re-enter a route, but no tester performed a re-entry action;
the tested action in those cells is the adjacent Land request.

The lesson is general enough to record: **a derived state phase describes what
the system did, and is not evidence that the tester did something.** The marker
now uses the producer's own recorded repeat cycle, which is intent rather than
consequence. The derived `re_entry` phase stays deliberately broader, and that
difference is documented rather than removed.

### One action can be recorded by two observers

`terminate_owning_producer` then showed 24 firings over 16 attempts, with 8
failing their precondition. In the offboard producer-exit cells the reason
`source_process_exit` appears twice: once from the workload node with route
attribution, and once from the runner lifecycle without it. The second record
fails the precondition only because the first record already set the fault.

Route attribution does not separate them in general — in the dynamic cells the
runner's `external_component_exit` is the action, while the later
`external_component_unresponsive` carries the route and is a consequence.

The check therefore separates a repeat from an echo using the repository's own
identity discipline: a genuine repeat of an action always follows a new
activation, so a firing that shares its predecessor's activation identity is a
duplicate observation. Under that rule the offboard cells report 16 actions and
8 duplicates, and the capacity cells report 8 actions and 8 duplicates, since
exhausting the registration slots produces two rejection records per attempt.

This is an evidence-contract gap, not merely an analysis inconvenience. When
actions become runtime-selectable, the executor should record exactly one action
application carrying its decision identity, and the ambiguity disappears by
construction instead of being resolved by a rule.

## What consistency here does and does not establish

It establishes that six predicates, evaluated on state derived without any mode
label, are true wherever the corresponding action actually fired across the whole
retained corpus.

It does not establish that the predicates are *sufficient* — no retained flight
attempted an action in a state where its precondition was false, because the
fixtures never tried. That direction can only be tested once the generator can
propose an action and be refused, which is a qualification obligation listed in
the conditional freeze.

It also does not establish reachability for `restart_producer_after_loss`, which
has no implementation.

## Reproduction

```bash
python3 -m scripts.corpus.precondition_check --root . --output-root <fresh dir>
```

The command refuses a non-empty output directory, refuses a declaration whose
precondition already holds in the empty initial state, and refuses an attempt
whose retained plan or trace is missing.
