# Producer reclaim — implemented, flown, recorded as unreachable

## What was attempted

`restart_producer_after_loss` was implemented and wired as a fourth selectable
action, and an 18-attempt non-formal qualification was run across two mechanisms
and three strategies.

Spec: [qualification.spec.json](qualification.spec.json).
Result: [qualification.result.json](qualification.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-c-restart-12eb3f4`.

## Result

The batch failed, and every failure was the reclaim. Fourteen attempts passed —
the three already-qualified actions were unaffected — and all four attempts that
selected the reclaim failed with one signature: accepted, admissible and
physically valid evidence, but no `action_requested` record and a safe-fallback
violation.

The reclaim never executed. This is a reachability finding about the fixtures
and the configured failsafe, not a defect in the decision path, and not a
statement about PX4.

## Why it is unreachable

**Legacy offboard: the window does not exist.** The configured offboard-loss
failsafe lands and disarms the aircraft about ten seconds after the producer is
lost. Worse, the runner observes the loss only by polling the producer process,
and in the recorded attempts it logged the loss *after* the aircraft had already
landed and disarmed:

```text
 41.80s  runner observed the producer loss
 41.84s  runner recorded the installed fallback
 42.6s   (telemetry) vehicle already landed and disarmed
 42.92s  attempt torn down
```

The executor was waiting to request the reclaim at the fallback plus five
seconds. There was never a moment at which the request could be both legal and
useful.

**Dynamic external mode: the loss is not synchronised with the anchor.** There
the loss is produced by a separate component whose exit timing is its own. In
the recorded attempt the requester released authority normally at its scheduled
completion and observed its successor at 17.2 s, and the runner only classified
the eventual process end as a loss at 41.8 s. The episode completed normally
instead of losing its producer.

An earlier measurement over retained evidence had shown windows of 7.7 s for the
offboard Land fallback and 11.6 s for the dynamic RTL fallback, which is why the
action's timing bounds were narrowed to 3.5–5.0 s before flying. Those windows
are measured from the fallback record in the closed trace. They are not
available to a live policy, because the runner's own view of the loss arrives
later than the trace suggests.

## What was done about it

The action is recorded as unreachable rather than quietly dropped or made to
pass. Its availability is `not_applicable` for legacy offboard and `new` for
dynamic external mode, and its note carries this evidence.

The failsafe configuration was **not** changed to create a window. Changing
`COM_OBL_RC_ACT` so the aircraft holds instead of landing after a producer loss
would make the action reachable, but it would also change the system under test
to fit the test, and it is a preregistration-level decision rather than a wiring
change.

The supporting infrastructure stays: `fallback_installed` remains an observable
marker with unit coverage, and the runner's reclaim hook remains inert because
no wired action can select it.

## What this costs the corpus

The conditional freeze proposed seven actions and argued for the reclaim
specifically, because it is the only proposed action whose legality depends on
the outcome of an earlier action — the property a feedback-free baseline cannot
exploit. That argument still holds, and the corpus now has no action with that
property.

Three options exist, and choosing between them is a preregistration decision:

1. preregister a failsafe configuration in which a producer loss installs Hold,
   which creates the window and is a documented change to the tested
   configuration;
2. give the runner a faster loss signal, so the loss is observed from telemetry
   at the moment the route is revoked rather than from process polling; or
3. accept a corpus with no state-dependent action, and state plainly in the
   evaluation that the feedback contrast is limited to coverage rather than
   legality.
