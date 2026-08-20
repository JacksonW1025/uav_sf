# Step D full-corpus qualification — PASS

## What was qualified

All seven proposed core actions selectable by policy in one corpus. Two
mechanisms, three strategies, three rounds, 18 attempts, explicitly non-formal
and with no attempt ledger.

Spec: [qualification.spec.json](qualification.spec.json).
Result: [qualification.result.json](qualification.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-d7-73a40b5`.

## Result

`PASS`. All 18 attempts were accepted, admissible, physically valid and
action-contract complete, all six units passed, and the state-aware feedback
check passed for both mechanisms. The batch exercised five of the seven actions
over eight distinct units, including both launch-configuration attempts.

The two decisions taken before this work are what made it possible.

**Registration capacity now times only the registration that must be refused.**
Starting all eight components on the policy's request had spanned the whole
active period and broken the moving profile twice. The seven legal slots are
filled during setup, so the timed action is the single refused registration,
which is also what the action is about.

**The health withhold is a launch configuration, not a runtime action.** It must
already be in effect when the activation it refuses is requested, so it has no
moment to choose and nothing to request. The policy still selects whether an
episode tests the rejection path; the runner applies it at launch and records
that it did, and the qualification accepts that shape.

## Four contract assumptions the launch configuration exposed

A refused activation never leaves the hover, and every one of these had encoded
"every episode moves" as if it were a fact about all experiments:

| Assumption | Where | Resolution |
| --- | --- | --- |
| The injection phase must name a motion phase | plan | the workload declares its own phases and injection phase |
| Motion progress thresholds must be positive | plan | a workload may declare `motion_required: false`, and then must not demand progress |
| The tested request is a transition request | physical contract | a refused transition is recorded as an activation request, and both count |
| An observed fault must follow motion entry | physical contract | vacuous when the workload declares no motion |

None of these was a defect in the flight. Each was a contract that could not
represent an honest plan, so it reported a violation for something the episode
never claimed to do. The strict obligations still apply by default, so every
plan written before this stays valid and unchanged.

The first attempt at the second row inferred motion from phase names, which was
brittle enough to reject a plan whose phase happened to be called `move`. The
declaration is explicit instead.

## Boundary

This is a non-formal qualification. It establishes that seven actions — six
timed and one applied at launch — can be selected by policy, applied, recorded
and fed back across both mechanisms. It establishes nothing about PX4 behaviour,
no defect, and no comparison between strategies.

All five signing conditions of the conditional freeze are now met.
