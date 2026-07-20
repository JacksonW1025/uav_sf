# N1 Trajectory Residue Adjudication

Date: 2026-07-20

Disposition: `CURRENT_EVENT_REOBSERVED_BUT_PHASE_DEPENDENT`

## Executive conclusion

The current-version natural event is real enough to retain as a narrow Route
input-use finding, but it is not a stable general outcome. Two independent
accepted late-cycle runs (`n1-c-a04`, `n1-c-a05`) reproduced the same
post-fallback old Trajectory-subject consumption seen in frozen
`freshness-f1-a02`. Five accepted early/mid-cycle runs did not reproduce it,
and the single accepted observation-reduced late-cycle confirmation was Route
PASS. This supports phase dependence and low-width runtime sensitivity; it
does not support a population rate, stable reproduction claim, proven source
root cause, or actuator-level physical consequence.

The Freshness pilot remains frozen at 16 attempts and 10 accepted runs. No N1
attempt was added to that denominator.

## Identity and method

- Preregistration commit: `54d0411bddbc62e28d05e006a844dedbf9ebe6b3`
- Formal-matrix starting commit: `088ee9ab0d21b08b34ade7a9539e5c91ae70cc8c`
- PX4: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`
- PX4 binary SHA-256: `d5cd7df0…71612`
- interface library: `c3e410f035806e8c56246708432ded09c976434b`
- Route Oracle: 0.4; Freshness Oracle: 0.1
- vehicle/scenario: `gz_x500`, Trajectory velocity `0.5 m/s`, total locally
  owned process termination, automatic RTL fallback

Phase was formed only by a legal local harness wait after an observed public
health reply. The study did not write PX4 health state or change controller,
setpoint, timeout, failsafe, mode, module, priority, or route semantics.

## Formal matrix

| Bucket | Meaning | Accepted | Attempts | Matching violations | Result |
|---|---|---:|---:|---:|---|
| A | 30 ms after reply | 2/3 | 6/6 | 0 | cap reached; measurement-insufficient cell |
| B | 150 ms after reply | 3/3 | 3/6 | 0 | target reached |
| C | 260 ms after reply | 3/3 | 5/6 | 2 | target reached; event reobserved |
| Total | bounded matrix | 8/9 | 14/18 | 2 | matrix stopped at all cell rules |

The six exclusions were three `OBSERVABILITY_REJECTED` attempts and three
`ENVIRONMENT_FAILURE` attempts. They do not enter the SUT denominator. A did
not reach its accepted target before its cell cap; no additional retry was
made.

All eight accepted runs had complete target windows, a VALID clock bridge,
complete route/controller/allocator/writer lineage, satisfied scenario
preconditions, Freshness `EXPOSURE`, and safe Land/Disarm cleanup. Six were
Route PASS and two were Route VIOLATION.

## Matching events

Both matching runs were in phase C:

| Run | Phase offset | Route change | Old-subject consumptions | Old epoch | External allocator | External writer |
|---|---:|---:|---:|---:|---:|---:|
| `n1-c-a04` | 260.058 ms | 30,752,000 us | 1 | 0 | 0 | 0 |
| `n1-c-a05` | 261.040 ms | 30,792,000 us | 2 | 0 | 0 | 0 |

In each case Commander declared and installed epoch 4 / RTL before the
position-controller observation carried the pre-fallback Trajectory subject.
Allocator and final-writer events after the route change were attributed to
the PX4 internal route, not the external route. Installation, exclusivity, and
continuity passed; Route revocation and recovery failed only on the narrow
controller-input rule.

## Observation-reduced confirmation

The trigger of two matching accepted violations required one accepted reduced
run, capped at three attempts. `n1-reduced-a01` was accepted on the first
attempt, so execution stopped:

- phase offset: 260.052 ms;
- logger profile: strict subset of the full N1 logger profile, hash
  `4d06e625…0536`;
- complete required windows, physical evidence, lineage, and cleanup;
- full trace events: 14,857, versus 21,835–21,865 in the two matching full
  observation runs;
- Route PASS, Freshness EXPOSURE, zero post-revocation residue.

This negative confirmation prevents a stable-reproduction claim. It does not
erase the two evidence-complete matching runs, and unused reduced seeds were
not executed.

## Source-level candidate explanation

The strongest candidate is retained Trajectory input across a route change
that keeps multicopter position control enabled:

1. Commander selects the failsafe route, updates `nav_state` and executor, and
   publishes a new route epoch before the new control mode
   (`Commander.cpp:2531–2588`).
2. RTL keeps the multicopter position cascade enabled when Commander publishes
   `vehicle_control_mode` (`Commander.cpp:2800–2816`).
3. Multicopter position control clears `_setpoint` only on an enabled→disabled
   position-control transition (`MulticopterPositionControl.cpp:403–414`).
4. If no new Trajectory message is available, `update(&_setpoint)` retains the
   local value; the observation carries its subject timestamp
   (`MulticopterPositionControl.cpp:441–449`).
5. Because position control remained enabled, the ordinary timestamp guard can
   pass and the same local `_setpoint` is supplied to
   `setInputSetpoint()` (`MulticopterPositionControl.cpp:454–559`).

This makes a pure label-only artifact unlikely for the matching cycles: the
observed object is also the candidate applied input. Confidence remains
`MODERATE`, not causal proof, because the observation is emitted before the
final branch and no old external lineage was observed at allocator or writer.
The result is therefore not evidence of post-revocation external authority or
of threshold-exceeding physical effect.

## Minimal testcase and evidence

The bounded regression specification is
[`minimal_testcase.yaml`](../../experiments/motivation/n1_trajectory_residue/minimal_testcase.yaml).
It uses phase C, the unchanged runner and binary, and treats a Route PASS as a
valid negative result rather than authorization to retry. Compact adjudication
data is in
[`n1_adjudication.json`](../../data/processed/motivation/n1_trajectory_residue/n1_adjudication.json).
Raw ULogs and logs remain ignored under
`runs/motivation/n1_trajectory_residue/` (158 MiB, 254 files at closure); none
is tracked.

## Limits and paper use

- The formal accepted target was 8/9 because A exhausted its cap at 2/3.
- The evidence localizes the two new events to the late health-cycle bucket,
  but three accepted C runs plus one reduced run cannot estimate occurrence
  probability.
- No behavior patch or upstream issue was created.
- The finding motivates route-aware runtime checks and lifecycle timing
  variation. It must be presented separately from Freshness `EXPOSURE` and
  from any claim of physical consequence.

N1 is complete. C1 is the next authorized phase; no full Stateful Fuzzer
campaign starts here.
