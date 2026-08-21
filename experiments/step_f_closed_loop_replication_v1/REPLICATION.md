# Step F: independent replication of the closed-loop batch

Non-formal. No formal ledger was opened and no denominator was created.

Same image and host as
[the first batch](../step_f_closed_loop_qualification_v1/QUALIFICATION.md),
independent strategy and simulation seeds, run through
`run_strategy_qualification`. The seeds were changed deliberately: if the
mechanism difference survives a different set of (action, timing) draws, it is
not a property of the ones drawn once.

## Result: 13 of 18, the gate did not pass

As before, the failures are safety stops rather than anything unrelated to what
is tested. All eighteen were admissible; the central real-time factor held at
0.9988 to 0.9994 across the batch.

## The mechanism difference replicated exactly

Over both batches, 36 attempts:

| mechanism | attempts | reclaim completely installed | not installed | safety stops |
| --- | --- | --- | --- | --- |
| `dynamic_external_mode` | 18 | **0** | 17 | 3 |
| `legacy_offboard` | 18 | **11** | 7 | 5 |

Dynamic reached four of its five reclaim bins across the two batches and
offboard reached all five, so this is not a property of which timings were
drawn. The dynamic reclaim was requested in every one of its eighteen episodes
and completely installed in none.

The offboard reclaim is not reliable either, and that is the second half of the
result. It installs in 11 of 18, and when it does not, the aircraft is close
enough to the ground that the supervisor stops the attempt: offboard has more
safety stops than dynamic, not fewer. The difference between the mechanisms is
not that one works and the other does not — it is that one sometimes completes
the installation inside the failsafe descent and the other never does.

## What is unchanged from the first batch

* Every decision log re-derived against its frozen policy, in all twelve units
  across both batches, without a divergence.
* The bounded-random policy again produced one-action episodes alongside
  two-action ones, so the sequence length is chosen rather than fixed.
* Both obligation branches again occur, each attempt judged against the
  obligations its own trace selected.

## A tooling finding, recorded because it cost two void batches

Between the batches, two attempts to re-fly the three offboard cells alone used
a script written for the occasion rather than the driver. Both produced 0 of 9,
almost all observability-rejected, with the central real-time factor at 0.56 to
0.86. The first was wrongly blamed on analysis running on the host; the second
was flown with the host idle and failed identically.

The machine was not the cause: a single attempt flown alone on the same host and
image was accepted at 0.9991, and this batch — same host, same image, same
three-at-a-time concurrency, real driver — held 0.999 across all eighteen. The
difference between that script and the driver has not been found. Their slot
assignment, CPU-set selection, barrier check and `_parallel` calls read the
same.

Nothing in the tooling reports a real-time factor collapse until the attempt is
rejected after the fact.

## Artifacts

* `qualification.spec.json` — the frozen batch specification.
* `qualification.result.json` — per attempt, per unit, and the gate.
* `environment-attestation.json` — the attested image and host.
