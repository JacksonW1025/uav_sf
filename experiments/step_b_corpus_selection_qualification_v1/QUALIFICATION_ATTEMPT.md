# Step B corpus-selection qualification — PASS

## What was qualified

The first live exercise of the corpus decision surface: the policy selects an
action and a timing from the declared corpus, and the flight must perform
exactly that action. Two mechanisms, three strategies, three rounds, 18
attempts, explicitly non-formal and with no attempt ledger.

Spec: [qualification.spec.json](qualification.spec.json).
Result: [qualification.result.json](qualification.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-b-2c6b754`.

## Result

`PASS`. All 18 attempts were accepted, admissible, physically valid, and
action-contract complete, and all six mechanism-by-strategy units passed. The
run opened no formal ledger and contributes to no denominator.

| Mechanism | Strategy | Units selected across three rounds |
| --- | --- | --- |
| legacy offboard | official sequence | stall:boundary, stall:boundary, stall:boundary |
| legacy offboard | bounded random | stall:post_boundary, exit:pre_boundary, stall:late |
| legacy offboard | state-aware | exit:boundary, stall:boundary, stall:post_boundary |
| dynamic external mode | official sequence | stall:boundary, stall:boundary, stall:boundary |
| dynamic external mode | bounded random | exit:pre_boundary, stall:boundary, stall:late |
| dynamic external mode | state-aware | stall:boundary, exit:boundary, exit:pre_boundary |

`stall` is `stop_owned_setpoint_stream` and `exit` is
`terminate_owning_producer`. Across the batch the policies applied the stall 13
times and the producer termination 5 times, over 5 distinct (action, timing)
units.

Three properties matter here:

- **The action is chosen, not configured.** Before this change a launch could
  only choose among five timing offsets for an action its matrix cell had
  fixed. Here both actions were selected by the policy and carried through to
  the aircraft, in both mechanisms.
- **The official sequence stayed deterministic**, holding its single registered
  unit in all six of its attempts, which is what its contract requires.
- **Feedback moved the state-aware selection.** For both mechanisms the check
  that later decisions consumed the coverage of earlier ones passed: each
  subsequent attempt saw exactly the units its predecessors had covered and
  selected a unit it had not.

## What it took, and what that says

The path only worked after four integration defects were found by running it,
none of which a host-side test could reach: the decision never reached the
container in corpus mode; the `run_sitl` guard compared a core action identity
against a runtime fault mode; the in-flight executor read the single-action
coverage key; and the batch summary read those keys and aborted on one rejected
attempt.

The most substantive of them was not a key mismatch. The workload applies the
fault mode it is *launched* with, so a policy could name one action while the
flight performed another. Each wired action now carries a live profile that
fixes its runtime fault mode and its contract obligations, and the launch
parameters and plan are derived from the selected action.

## Two environment findings

**Machine quiet time is a qualification precondition.** An earlier batch of the
same spec, on the same image, had every attempt rejected for clock uncertainty
above the registered bound. An unpinned remote-desktop process was taking about
two cores from the pinned container CPU sets, and the central real-time factor
fell to 0.563 against 0.999 here. The bound was not relaxed; the machine was
quietened.

**The clock fit still flakes at a low rate.** The run before this one passed 17
of 18, with one attempt rejected at a central real-time factor of 0.9989 and a
median of 0.99993 — good simulation timing, but a cross-domain fit above the
20 ms bound. Passing attempts in that batch fit at 1.2 ms and 6.2 ms. One
re-run was taken, and only one; the observed rate is one flake in 36 attempts
across the two clean batches. A gate that requires 18 of 18 will therefore fail
occasionally for reasons unrelated to what it tests. That is worth deciding
about before a fixed-budget campaign, and it is recorded rather than tuned away.

## Plan error corrected along the way

The first clean batch failed three attempts on a safe-fallback violation, all
of them dynamic external mode with the producer-termination action. The cause
was in the spec, not the system: when a dynamic external mode producer is lost,
PX4 installs internal RTL, not Land, and the retained process-exit study had
preregistered RTL for exactly that reason. The spec now declares the fallback
per mechanism. The successor a workload requests after a completion and the
fallback the system installs after a fault are different obligations.

## Boundary

This is a non-formal qualification. It establishes that live action selection
executes, records, and feeds back correctly for the two wired actions. It
establishes nothing about PX4 behaviour, no defect, and no comparison between
strategies. The corpus freeze remains unsigned: three of its five signing
conditions — closing the availability gaps, implementing the restart action,
and wiring the registration and health actions — are still open.
