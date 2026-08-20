# Step F: the closed-loop qualification

Non-formal. No formal ledger was opened and no denominator was created. An
Oracle violation here is accepted evidence, not a failed attempt.

Image `uav-sf-family-a-thor:step-f-6c492f3`, attested. Six cells over two
mechanisms and three strategies, three rounds each, two-phase barrier.

## Result: 15 of 18, the gate did not pass

The gate requires every attempt to be accepted. Three were
`FORMAL_SAFETY_STOP`: the independent safety supervisor stopped them, twice for
unexpected ground contact and once for exceeding the vertical speed bound.

Nothing failed for a reason unrelated to what this tests. All eighteen were
admissible, all eighteen were physically valid, and the clock fit held in every
one of them.

## What the batch establishes

**The loop chose, and every choice re-derives.** All six units replayed their
decision logs against their frozen policies without a single divergence. The
flight is trusted for the state it observed and for nothing else; the choice
made from that state is recomputed, and it matched every time.

**The sequence length is chosen, not fixed.** The bounded-random policy
produced two-action and one-action episodes in the same cell — `[2, 1, 2]` for
offboard and `[2, 2, 1]` for dynamic. An episode that stopped after the
termination recorded stopping as a decision, which is what keeps it distinct
from an episode that ran out of time.

**Both obligation branches occur in real evidence.** Twelve episodes resolved
to `when_absent` and five to `when_observed`, each judged against the
obligations its own trace selected. The conditional plan is doing work: the
same launch is held to a completely installed fallback or to a completed
reclaim depending on what the flight did, and neither obligation had to be
switched off to make the other possible.

**Timing bins are reached.** Across the batch the policies placed actions in
every bin: early, pre_boundary, boundary, post_boundary and late.

## The finding: the two mechanisms differ at the reclaim

This is what the batch is for, and it is not visible in any retained evidence.

| mechanism | reclaim completely installed | reclaim activation | failsafe |
| --- | --- | --- | --- |
| `legacy_offboard` | 5 of 6 | about 3.7 s | `internal_land` |
| `dynamic_external_mode` | **0 of 9** | about 11 s | `internal_rtl` |

Every dynamic episode resolved to `when_absent`: the reclaim was requested, the
producer restarted, and the tested route never installed completely before the
episode ended. Reading one timeline, the reclaim producer restarts at 8.033 s
and the mode is not observed active until 19.363 s. It is a new process, so it
must register the external mode again, wait for PX4 to assign it a mode
identifier, and only then request activation. The offboard producer has no
registration protocol to repeat and is active 3.7 s after restart.

Against that, the window is not generous. Measured from the telemetry-visible
fallback to the end of the episode, dynamic has 13.1 to 15.8 s and is under a
return-to-launch descent for all of it. Registration consumes most of it, and
the three safety stops are what happens at the end: the reclaim arrives while
the aircraft is close to the ground under a descending failsafe.

## Why no retained evidence shows this

The retained single-action reclaim never terminated a producer that held
authority. In `step-cr-q-offboard-random-001` the producer completed at 8.045 s,
released to its successor at 8.124 s and exited at 9.645 s, and the reclaim
started 133 ms later. Its executor cannot distinguish a requested handover from
a fallback — Hold is Loiter — so it anchored the reclaim after the completion.
The aircraft was loitering, not descending, and the reclaim had as long as it
wanted.

The ten-second reclaim window recorded in Step C was measured under that
loiter. The real failsafe descends.

## What this does not settle

Whether the dynamic reclaim is reachable at all under a real producer loss is
now an open question rather than an assumption. Three readings are available and
none is taken here:

* the difference is the result — a route-replacing mechanism that must
  re-register cannot reclaim inside its own failsafe window, which is a
  property of the mechanism and belongs in the comparison;
* the timing bins are wrong for the dynamic mechanism and need re-measuring
  against a descending failsafe rather than a loiter; or
* the reclaim is offboard-only in practice, as the registration actions are
  dynamic-only, which would change a signed availability.

The first is a claim about the system, the second about this fixture, and the
third about the corpus. They are distinguishable by measurement and are not
distinguished yet.

## Artifacts

* `qualification.spec.json` — the frozen batch specification.
* `qualification.result.json` — per attempt, per unit, and the gate.
* `environment-attestation.json` — the attested image and host.
