# Step C re-entry qualification — PASS

## What was qualified

Route re-entry as a policy-selected live action, on both compared mechanisms,
alongside the two actions Step B qualified. Two mechanisms, three strategies,
three rounds, 18 attempts, explicitly non-formal and with no attempt ledger.

Spec: [qualification.spec.json](qualification.spec.json).
Result: [qualification.result.json](qualification.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-c-38064db`.

## Result

`PASS` on the first batch. All 18 attempts were accepted, admissible,
physically valid and action-contract complete, all six units passed, and the
state-aware feedback check passed for both mechanisms.

| Mechanism | Strategy | Units selected across three rounds |
| --- | --- | --- |
| legacy offboard | official sequence | stall:boundary ×3 |
| legacy offboard | bounded random | re-entry:late, stall:pre_boundary, re-entry:late |
| legacy offboard | state-aware | exit:boundary, stall:boundary, re-entry:boundary |
| dynamic external mode | official sequence | stall:boundary ×3 |
| dynamic external mode | bounded random | exit:late, re-entry:post_boundary, exit:pre_boundary |
| dynamic external mode | state-aware | exit:boundary, re-entry:boundary, stall:boundary |

Across the batch the policies applied the stall 9 times, the producer
termination 4 times and the re-entry 5 times, over 8 distinct (action, timing)
units. Both state-aware cells visited all three actions in their three rounds.

## What re-entry produced

In a re-entry attempt the tested route is entered twice in one episode, and the
two entries are separated by identity rather than by name:

```text
dynamic_external_mode  px4-epoch-4  nav-23-epoch-4
dynamic_external_mode  px4-epoch-6  nav-23-epoch-6
```

The derived semantic state reaches route epoch index 2 and visits the `re_entry`
phase. This is the observation Stage A1 recorded as a finding — two successful
entries under one mode name can only be told apart by epoch and activation
identity — now produced on demand by a policy rather than by a fixture constant.

## What it took

The dynamic requester had no repeat-cycle loop at all, so re-entry existed only
for legacy offboard. It now re-requests its registered mode from the installed
safe route, keeping the component registered so the two entries differ by route
epoch and activation identity.

In both nodes re-entry previously fired on a fixed successor dwell, which a
policy cannot schedule. Both now take a `scheduled_action` parameter and, when
the policy selected re-entry, wait for the executor's request instead. The
action anchors its timing on `successor_installed` rather than on route
activation, through the anchor mechanism added earlier in Step C.

The qualification cell uses `successor_route: internal_hold`. Re-entering from a
landing successor would be a different experiment.

A latent defect surfaced while wiring this: an unset action-request path was
being passed to the workload nodes as an empty ROS parameter override, which the
parameter parser rejects outright. Any run without a strategy decision would
have failed at node startup. Empty overrides are now omitted.

## Boundary

This is a non-formal qualification. It establishes that three actions can be
selected by policy, applied, recorded and fed back on both mechanisms. It
establishes nothing about PX4 behaviour, no defect, and no comparison between
strategies.

The corpus freeze remains unsigned. Two of its five signing conditions are still
open: `restart_producer_after_loss` is not implemented, and the registration and
health actions are not yet selectable.
