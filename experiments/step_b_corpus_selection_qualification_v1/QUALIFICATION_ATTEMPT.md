# Step B corpus-selection qualification — attempted, not signed

## What was attempted

The first live exercise of the corpus decision surface: the policy selects an
action and a timing from the declared corpus, and the flight must perform
exactly that action. Two mechanisms, three strategies, three rounds, 18
attempts, explicitly non-formal and with no attempt ledger.

Spec: [qualification.spec.json](qualification.spec.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-b-2c6b754`.

## Outcome: the run does not qualify

All 18 attempts were rejected before evaluation with
`clock uncertainty exceeds the configured bound`. No admissible evidence was
produced, so nothing here may be cited as a qualification result and the
corpus freeze stays unsigned.

The cause is environmental, not a property of the decision path. The batch
pins three containers to disjoint CPU sets, but an unpinned remote-desktop
process was consuming roughly two cores for the duration. The simulation
therefore fell behind real time in its central window, and the cross-domain
clock fit exceeded the 20 ms bound the spec registers.

| Batch | Central real-time factor (lowest of the batch) | Result |
| --- | ---: | --- |
| Retained process-exit qualification | 0.999 | 18/18 accepted |
| This attempt | 0.563 | 0/18 admissible |

The startup minimum real-time factor is about 0.014 in both batches, so that
transient is not the difference; the central window is.

## What the attempt does establish

These observations come from the runtime and decision records, which are
unaffected by the clock closure that rejected the evidence. They are
engineering evidence that the path works, not a qualification result.

- 17 of 18 attempts applied exactly the action their decision selected, with
  the complete `strategy_decision → action_scheduled → action_requested`
  lifecycle recorded.
- The applied offset differed from the planned offset by 1.4 ms to 21.8 ms.
- 17 of 18 attempts satisfied the physical-validity contract.
- Selection genuinely varied and was mechanism-independent:

| Strategy | Units selected across its six attempts |
| --- | --- |
| `official_sequence` | `stop_owned_setpoint_stream:boundary` only, as its contract requires |
| `bounded_random_timing` | both actions, four distinct units |
| `state_aware` | both actions, four distinct units |

Before this change a launch could only choose among five timing offsets for an
action its matrix cell had already fixed. Here the action itself was chosen by
the policy and carried through to the aircraft.

One attempt (`step-b-q-offboard-official-002`) ended in an environment failure
with PX4 aborting, and did not reach its action.

## What must happen before this can be signed

1. Re-run the batch on a quiet machine, with no unpinned process competing for
   the container CPU sets.
2. Require, as this spec already does, that every attempt is accepted,
   admissible, physically valid, action-contract complete, and that the
   state-aware cells show coverage feedback moving between rounds.

The clock bound is not to be relaxed to make the batch pass. A loosened bound
would admit exactly the timing evidence these experiments exist to measure.
