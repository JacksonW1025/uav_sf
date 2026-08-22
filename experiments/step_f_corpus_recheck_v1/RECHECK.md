# Re-checking the signed corpus against real failsafe evidence

Non-formal, read-only. No formal ledger, no denominator, no retained artifact
edited.

The signed corpus was validated against 230 attempts in which
`restart_producer_after_loss` had **one** instance. Step F showed why: the
fixture that produced it reclaimed under a loiter, because its producer died
after releasing authority. The two closed-loop batches supply the missing
evidence — 36 episodes that terminate the producer while it owns the route and
reclaim under a real descending failsafe.

## Result: seven of seven consistent, over three times the evidence

265 attempts, 204 instances, no predicate inconsistent and none unvalidated.

| action | instances when signed | now |
| --- | --- | --- |
| `stop_owned_setpoint_stream` | 80 | 80 |
| `terminate_owning_producer` | 18 | **53** |
| `adjacent_land_request` | 30 | 30 |
| `re_enter_route_after_successor` | 23 | 23 |
| `withhold_health_reply` | 11 | 11 |
| `exhaust_registration_capacity` | 8 | 8 |
| `restart_producer_after_loss` | **1** | **12** |

The two actions the closed loop exercises are the two that grew. The reclaim
predicate now holds across twelve firings under a real failsafe rather than one
under a loiter.

## A defect the extra evidence exposed, in the checker

The first run of this replay reported the reclaim inconsistent, one violation in
twelve. It was not the predicate.

`timed_decision_times` reads the executor's own record to find when an action
was applied, and it recognised only `action_requested`. The closed loop records
`closed_loop_applied` for that moment. Unrecognised, every closed-loop action
fell back to being judged at its effect — which is the rule for a launch
configuration, not for a timed action, and is exactly the distinction Step E
established. Judged at its effect, one reclaim landed on a state whose lineage
was still partial.

With the record recognised, all twelve are judged at their decision moment and
all twelve satisfy the predicate. The states move too, from
`internal_navigator | executing` to `internal_safe | fallback`, which is what
the reclaim's precondition describes.

## The reclaim window, re-measured under a real failsafe

Step C recorded about ten seconds from the telemetry-visible fallback to
disarm. That was measured under the loiter. Over these 36 episodes:

| mechanism | fallback to touchdown | fallback to disarm |
| --- | --- | --- |
| `legacy_offboard` | 5.93 – 22.75 s, median **20.66 s** | median 22.67 s |
| `dynamic_external_mode` | 9.81 – 12.27 s, median **10.98 s** | median 12.99 s |

Set against the reclaim's own cost — 3.3 to 6.4 s for offboard, 9.9 to 13.1 s
for dynamic — this is the whole result in two numbers. Offboard spends about a
quarter of its window and installs the reclaim in 11 of 18. Dynamic spends
essentially all of it and installs in none.

Two independent factors run against the dynamic mechanism, not one: its reclaim
is slower, *and* its window is shorter. The ten-second figure was close to the
dynamic window by coincidence and roughly half the offboard one.

## Artifacts

* `precondition-check.json` — per action, per cell.
* `per-instance.jsonl` — every firing, with the state it was judged on.
* `core-actions.json` — the declarations as replayed.

Reproduce with:

```bash
python3 -m scripts.corpus.precondition_check --root . --output-root <fresh dir> \
  --qualification-study step-e-signed-corpus-qualification-v1 \
  --qualification-study step-f-closed-loop-qualification-v1 \
  --qualification-study step-f-closed-loop-replication-v1
```
