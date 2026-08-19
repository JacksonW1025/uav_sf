# Step C adjacent-request qualification — PASS

## What was qualified

The adjacent Land request as a policy-selected live action on both compared
mechanisms, alongside the four actions already qualified. Two mechanisms, three
strategies, three rounds, 18 attempts, explicitly non-formal and with no attempt
ledger.

Spec: [qualification.spec.json](qualification.spec.json).
Result: [qualification.result.json](qualification.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-c-adj-bf5d8d7`.

## Result

`PASS`. All 18 attempts were accepted, admissible, physically valid and
action-contract complete, all six units passed, and the state-aware feedback
check passed for both mechanisms. Five actions are now selectable, and this
batch exercised four of them over six distinct units.

The request lands where it was aimed:

| Selected bin | Recorded bucket | Offset from the completion |
| --- | --- | ---: |
| `adjacent_land_request:boundary` | near | +4 ms |
| `adjacent_land_request:post_boundary` | after | +270 ms |

The bins are 250 ms apart, and the measured separation matches. The bucket
vocabulary is the one the Stage A1 timing cells used, so a request aimed at the
boundary is recorded as `near` and one aimed past it as `after`.

## Two timing defects found by measuring, not by testing

Both were caught by comparing the recorded request against the completion it
was supposed to straddle. Both would have passed a qualification that only
asked whether the action executed.

**Starting the requester on demand cost 600 ms.** That is wider than the 250 ms
spacing between the bins the action exists to distinguish, so every bin was
shifted later than decided. The node now starts with the workload and fires on
a trigger file, so it is already running when the decided moment arrives.

**The anchor was progress-based while the completion is time-based.** The bins
were anchored on motion entry, which the vehicle reaches when it has travelled
0.75 m — about three seconds after the route activates. Every bin therefore
landed about that much late: a request aimed at the boundary was measured 3.4 s
past it, and neighbouring bins were 69 ms apart instead of 250 ms. Both
producers measure their active period from route activation, so that is now the
anchor.

While diagnosing the second one, the two mechanisms appeared to anchor their
completions differently, which would have broken the shared-task-shape premise
of the moving comparison. They do not: the offboard producer sets its motion
start on the first tick after activation, so both complete at activation plus
the active period. A fixture change was drafted on that misreading and reverted
before it was flown.

## Boundary

This is a non-formal qualification. It establishes that five actions can be
selected by policy, applied at the intended moment, recorded and fed back on
both mechanisms. It establishes nothing about PX4 behaviour, no defect, and no
comparison between strategies.

The corpus freeze is one condition from being signable: the registration and
health actions remain cell-configured rather than selectable, and they need live
markers the executor cannot observe yet.
