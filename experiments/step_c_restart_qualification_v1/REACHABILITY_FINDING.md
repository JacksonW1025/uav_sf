# Producer reclaim — unreachable, then made reachable by fixing the measurement

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

## Resolution: the measurement was wrong, not the window

The second option was taken, because it corrects a measurement rather than the
system being measured. The failsafe configuration is unchanged.

The loss is now derived from telemetry — the first safe internal navigation
state observed after the tested route was active — instead of from the runner
noticing the producer process is gone. The runner's own record survives as a
last resort and the earlier of the two is used, and the reclaim now starts from
the main loop rather than from the branch that waits for that notice.

Two further defects surfaced once the reclaim actually executed:

- **Its plan required a fallback it exists to preempt.** The trace shows the
  safe route activated, triggered and then revoked as the reclaim took over, so
  a completely installed fallback was a self-contradictory obligation. The
  reclaim no longer expects one; the fault is still expected.
- **Its timing bins were measured in the wrong window.** Bins of 3.5 to 6.5 s
  after an anchor are far too late when the window closes on touchdown, and the
  supervisor correctly stopped those attempts on unexpected ground contact.
  Timing bins now belong to the action: still five ordered discrete values, so
  systematic enumeration stays well defined, but the reclaim's span 0.5 to
  2.5 s.

## Result after the fix

`PASS`, 18 of 18, with four selectable actions and seven distinct units. A
reclaim attempt runs the full state-dependent sequence:

```text
legacy_offboard  px4-epoch-4   completed and revoked
internal_hold    px4-epoch-5   installed, then the producer is lost
fallback         internal_hold triggered, then revoked
legacy_offboard  px4-epoch-7   reclaimed by a new producer session
```

The runner records the new session as `reclaim-<attempt>`, so the reclaimed
route is separated from the lost one by producer session and route epoch rather
than by mode name. The corpus keeps the action whose legality depends on the
outcome of an earlier action, which is what the seven-action selection was
argued from.
