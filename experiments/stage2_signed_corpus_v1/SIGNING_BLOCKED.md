# Corpus signing — blocked on one modelling decision

## What this directory is

The precondition replay that a signed corpus must carry, re-run over the whole
current evidence base: 303 attempts, 213 from the five closed formal studies and
90 from the five non-formal qualifications this stage produced.

Result: [precondition-check.json](precondition-check.json), per instance in
[per-instance.jsonl](per-instance.jsonl), declarations in
[core-actions.json](core-actions.json).

**The corpus is not signed.** Two of seven predicates report an inconsistency,
both from the same cause and both in the same attempt.

## Result

| Action | Status | Actions | Duplicate observations | Precondition held |
| --- | --- | ---: | ---: | ---: |
| `stop_owned_setpoint_stream` | consistent | 119 | 0 | 119 |
| `terminate_owning_producer` | inconsistent | 37 | 17 | 36 |
| `adjacent_land_request` | consistent | 33 | 0 | 33 |
| `re_enter_route_after_successor` | consistent | 37 | 0 | 37 |
| `withhold_health_reply` | consistent | 10 | 0 | 10 |
| `exhaust_registration_capacity` | consistent | 8 | 8 | 8 |
| `restart_producer_after_loss` | inconsistent | 1 | 0 | 0 |

Nothing is unvalidated any more: the reclaim now has a marker, and the
qualification evidence supplies instances for the four actions the formal corpus
never exercised.

## The one cause

Both inconsistencies are in `step-cr-q-offboard-random-001`, the reclaim
episode, and both are about *when an effect is recorded* rather than *when the
action was taken*:

```text
seq 10474  terminate_owning_producer   state before: internal_safe holds authority
seq 12674  restart_producer_after_loss state before: px4_internal holds authority
```

The producer loss is recorded after the failsafe has already revoked the
external route, so at that sequence the external authority the predicate
requires is gone. The reclaim request is recorded while the vehicle sits in the
internal navigator state rather than one of the named safe routes the predicate
lists.

The live executor evaluates a precondition against the state at the moment it
decides. This replay evaluates it against the state at the moment the effect
appears in the trace. The two differ by the revocation latency, which is
negligible in every other episode and is not negligible here.

## The decision to take

Either:

1. **Evaluate against the decision moment.** The replay would need the executor's
   own decision time, which the strategy lifecycle records, and would compare
   the state at that time rather than at the effect. This measures what the
   generator actually knew.
2. **Widen the predicates to the recorded moment.** The producer termination
   would drop its "external authority still held" clause, and the reclaim would
   accept the internal navigator alongside the named safe routes. This measures
   what the evidence shows, and weakens two predicates.
3. **Record the reclaim episode as a known divergence** and sign the corpus with
   it noted, which leaves a predicate that is false where the action legally
   fired.

The first is the most faithful and the most work. The second is cheap and
loses the precision that made the predicates worth checking. The third signs a
record with a known inconsistency in it.

## The first option was tried, and it does not work as stated

Evaluating each precondition at the executor's recorded request time was
implemented and replayed. It did not resolve either inconsistency, and it
introduced two more: the health withhold went from consistent to two
violations.

The reason is that a launch configuration has no decision moment in the sense
the rule assumes. Its record is written during container setup, before the
episode has done anything, so its precondition — an activation requested and no
external route holding authority — is false at that instant for a reason that
has nothing to do with legality.

That splits the original question in two. A timed action has a decision moment
and could be judged there. A launch configuration's precondition describes the
state its effect is legal in, not the state it was configured in, so it must be
judged at its effect. A rule that serves both has to say which kind it is
looking at, which the corpus now knows and this replay does not yet use.

The change was reverted rather than kept, because a replay that reports four
inconsistencies instead of two is not closer to the truth.

Signing waits on that choice. Every other signing condition is met: the decision
interface selects an action and a timing, the availability gaps are closed, the
reclaim is implemented, and every action has a passing non-formal qualification.
