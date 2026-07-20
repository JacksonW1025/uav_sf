# Current-Version External Mode Setpoint Freshness Pilot Report

Date: 2026-07-20

Study: `current_version_external_mode_setpoint_freshness_pilot`

Final disposition: `CURRENT_NATURAL_VIOLATION_FOUND`

## Executive conclusion

The bounded pilot found one evidence-complete natural Route contract violation
on the locked current PX4 stack. In accepted Trajectory process-stop run
`freshness-f1-a02`, Route Oracle observed two controller consumptions after
fallback selection whose subject timestamp still identified the pre-fallback
Trajectory setpoint. Revocation and recovery are `VIOLATION`; installation,
exclusivity, and continuity are `PASS`. No post-revocation old-epoch
consumption, allocator input, or writer output was observed. This event was not
repeated in the other two accepted F1 runs, so the result is a found event, not
a violation-rate estimate.

This Route result is separate from the preregistered pre-revocation Freshness
classification. All 10 accepted runs return Freshness Oracle `EXPOSURE`, not
`VIOLATION`: the locked implementation has no enforced per-setpoint freshness
deadline, and every accepted context demonstrates continued use or influence
of the retained command. Nine accepted runs have Route `PASS`; a Route PASS
does not erase Freshness exposure.

The formal campaign stopped exactly at its frozen cell rules. F1, F3, and F4
each reached `3/3`. F2 reached its six-attempt cap at `1/3`, with five
observability rejections and no authority to continue. The planned matrix is
therefore `10/12`, and the Attitude context is separately classified
measurement-insufficient. That limitation does not erase the accepted,
evidence-complete natural violation that determines the overall disposition.

## 1. Frozen identity and boundary

The preregistration was pushed as
`be11b984e13c9df43ebc8b3b31d04517c46d5224` before F1. Its SHA-256 is
`fbbac59f943f499b6cc16e2787976c4ea1814dba1ce89efe8d40c23c0603f05f`.
Formal execution closed at checkpoint
`202d3a504cbaaa86a820b62be805e9c09566998b`.

| Component | Frozen identity |
|---|---|
| PX4-Autopilot | `4ae21a5e569d3d89c2f6366688cbacb3e93437c9` |
| px4-ros2-interface-lib | `c3e410f035806e8c56246708432ded09c976434b` |
| px4_msgs | `18ecff03041c6f8d8a0012fbc63af0b23dd60af1` |
| Freshness Oracle | `0.1`, schema `1.0` |
| Route Oracle | `0.4`, schema `1.3` |
| Vehicle/simulator | `gz_x500`, Gazebo SITL default world |

The frozen inputs were Trajectory velocity `[0.5, 0, 0] m/s`, Attitude roll
`0.12 rad` with body thrust Z `-0.72`, and Rate roll `0.06 rad/s` with body
thrust Z `-0.72`. The Rate process-stop and health-alive stall cells used the
same input, thrust, initial-state rule, five-second settling period,
three-second target, two-second recovery dwell, and seed schedule. Only the
controlled failure condition differed.

No PX4 control behavior, health-loss policy, setpoint-timeout behavior, or
physical/acceptance threshold was changed during the formal pilot. Raw run
artifacts remain ignored under `runs/motivation/freshness/`.

## 2. Attempt accounting

| Cell | Context | Accepted / attempts | Cell result | Freshness on accepted runs | Route on accepted runs |
|---|---|---:|---|---|---|
| F1 | Trajectory + process stop | 3 / 3 | complete | 3 EXPOSURE | 2 PASS, 1 VIOLATION |
| F2 | Attitude + process stop | 1 / 6 | measurement-insufficient at cap | 1 EXPOSURE | 1 PASS |
| F3 | Rate + process stop | 3 / 4 | complete | 3 EXPOSURE | 3 PASS |
| F4 | Rate + setpoint-only stall | 3 / 3 | complete | 3 EXPOSURE | 3 PASS |
| **Total** |  | **10 / 16** | **10/12 planned accepted** | **10 EXPOSURE** | **9 PASS, 1 VIOLATION** |

The six rejected attempts are all observability rejections: five in F2 and one
in F3. There were zero environment failures, campaign-configuration failures,
or formal safety stops.

F2 attempts 1, 2, 5, and 6 exceeded the unchanged `1.0 m` pre-fault altitude
span; attempt 1 also had a `DEGRADED` clock bridge. Attempt 3 selected a VALID
bridge whose valid interval began after the fault marker. F3 attempt 3 had
complete route/fallback windows but no required health-loss timestamp, leaving
Freshness fallback clauses `UNKNOWN`. None of these attempts enters the SUT
denominator. Every attempt completed cleanup and landed/disarmed.

## 3. Pre-revocation command exposure and fallback timing

For `TOTAL_PROCESS_STOP`, the formal physical and command-exposure window ends
at automatic fallback installation. For `SETPOINT_ONLY_STALL`, it ends at the
bounded target-window end. Recovery and later explicit cleanup are excluded
from these values.

| Cell | Accepted n | Maximum retained-setpoint age, ms (min / median / max) | Health loss after fault, ms | Fallback installed after fault, ms |
|---|---:|---:|---:|---:|
| F1 Trajectory stop | 3 | 1096 / 1104 / 1348 | 1074.042 / 1113.306 / 1352.638 | 1086.042 / 1125.306 / 1364.638 |
| F2 Attitude stop | 1 | 1320 | 1300.038 | 1312.038 |
| F3 Rate stop | 3 | 1116 / 1248 / 1312 | 1095.211 / 1237.347 / 1303.543 | 1107.211 / 1249.347 / 1315.543 |
| F4 Rate stall | 3 | 2732 / 2748 / 2780 | not expected; health alive | not expected; route retained |

All seven accepted process-stop runs detected health loss within the frozen
`1500 ms` deadline and installed automatic RTL within `12 ms` of the observed
health-loss timestamp, well inside the `250 ms` post-detection deadline. Their
retained-command use before that fallback is the preregistered design exposure,
not an explicit freshness-policy violation.

## 4. Bounded health-alive route retention

All three F4 target windows exceed the frozen three-second monotonic target:
`3031.517`, `3037.872`, and `3053.964 ms`. Across those windows, all 26 observed
health requests have matching replies, no health loss or automatic fallback is
observed, the external route remains installed at each target end, and no
ground contact occurs.

The mapped PX4 lineage shows retained-setpoint ages of `2732–2780 ms` and last
controller influence `2735.665–2784.032 ms` after the fault marker. The shorter
PX4-clock interval than the monotonic wall target is reported rather than
silently equated across clocks. The complete monotonic window proves the
health-alive policy condition; the VALID bridge and PX4 timestamps bound the
command-age and lineage measurements.

This is the source-predicted differential: process death removes both setpoint
and health replies and eventually installs RTL, whereas a setpoint-only stall
leaves health alive and retains the external route for the complete bounded
window. All three stall runs are Freshness `EXPOSURE` and Route `PASS`.

## 5. Physical consequence by setpoint level

The following ranges use only the formal pre-revocation/target physical window.
The frozen thresholds were `45 deg` attitude excursion, `3 rad/s` angular-rate
excursion, `1 m` altitude loss, and `3 m` horizontal displacement.

| Cell | Attitude excursion, deg | Angular rate, rad/s | Altitude loss, m | Horizontal displacement, m | Threshold consequence |
|---|---:|---:|---:|---:|---|
| F1 Trajectory stop, n=3 | 0.459–0.489 | 0.017–0.037 | 0.029–0.048 | 0.538–0.645 | none exceeded |
| F2 Attitude stop, n=1 | 6.677 | 0.032 | 0.000 | 5.741 | horizontal exceeded |
| F3 Rate stop, n=3 | 13.991–14.311 | 0.031–0.033 | 0.319–0.700 | 5.914–7.227 | horizontal exceeded |
| F4 Rate stall, n=3 | 16.325–16.413 | 0.032–0.033 | 1.389–1.765 | 17.881–18.181 | altitude and horizontal exceeded |

These measurements establish a scenario-specific consequence gradient across
the frozen setpoints; they are not a controller-performance ranking or a claim
that all vehicles will produce the same motion. No accepted target window had
ground contact, and the attitude/rate safety limits were not approached.

## 6. Recovery and cleanup consequence

Recovery begins only after automatic fallback installation or the bounded
stall target end. It is never combined with the formal exposure clause.

| Cell | Recovery attitude, deg | Recovery rate, rad/s | Recovery altitude loss, m | Recovery horizontal displacement, m | Full post-fault horizontal, m |
|---|---:|---:|---:|---:|---:|
| F1, n=3 | 3.228–3.697 | 0.231–0.252 | 0.003–0.006 | 0.321–0.343 | 0.872–0.965 |
| F2, n=1 | 14.560 | 1.564 | 0.005 | 6.186 | 11.924 |
| F3, n=3 | 14.008–14.330 | 0.498–1.488 | 0.163–0.310 | 10.232–10.546 | 16.146–17.773 |
| F4, n=3 | 16.437–16.537 | 0.632–1.410 | 1.029–1.135 | 15.519–16.040 | 33.400–34.164 |

Process-stop runs installed automatic RTL. Health-alive stall runs used the
frozen explicit sequence Hold, recovery dwell, Land, and Disarm. All accepted
runs and all rejected attempts terminated landed and disarmed with no simulator
clock stall. The larger F4 cleanup displacement is visible and interpretable;
it does not retroactively enlarge or reclassify the bounded target-window
physical clause.

## 7. Route Oracle result

Accepted run `freshness-f1-a02` is the sole Route `VIOLATION`. Its declared
Trajectory-to-RTL transition occurs at PX4 time `30168000 us`. Route Oracle
records two post-revocation controller consumptions carrying the old
Trajectory subject timestamp, so revocation and recovery fail. The same result
records:

- zero post-revocation old-epoch consumptions;
- zero post-revocation allocator inputs and writer outputs;
- fallback installation complete in `24 ms`;
- no writer overlap and a zero-millisecond maximum unowned window;
- installation, exclusivity, and continuity `PASS`.

The classification is
`NATURAL_POST_FALLBACK_STALE_TRAJECTORY_CONSUMPTION`. It is a narrow observed
Route-attribution violation after fallback, not evidence that allocator/writer
authority remained external and not a rewriting of the pre-revocation
Freshness window. The other two accepted F1 runs and every accepted F2–F4 run
have Route `PASS`, so reproduction and event frequency remain unresolved.

## 8. Freshness Oracle result

Freshness Oracle returns `EXPOSURE` for every accepted run:

- F1 `3/3`: retained Trajectory command use until health-driven fallback;
- F2 `1/1` accepted: retained Attitude command plus horizontal physical
  threshold exposure, with the planned three-run context incomplete;
- F3 `3/3`: retained Rate command plus horizontal physical exposure until
  fallback;
- F4 `3/3`: retained Rate command and external route for the complete
  health-alive target, plus altitude and horizontal physical exposure.

No enforced setpoint timeout applies on the locked revision. Consequently,
retained use is `EXPOSURE` under the frozen interpretation rule unless another
explicit contract is violated. The F1 Route violation is that separate
contract result; Freshness remains `EXPOSURE` because its bounded
pre-revocation clauses and health/fallback deadlines are satisfied.

## 9. Relationship to PX4 Issue #27514

[PX4-Autopilot Issue #27514](https://github.com/PX4/PX4-Autopilot/issues/27514)
describes the same qualitative mechanism: no external setpoint freshness check,
retention of the last command, dependence on the separate arming-check health
path after process death, setpoint-level consequence differences, and a
health-alive setpoint stall.

The pilot confirms that qualitative mechanism on the exact locked stack. It
does not reproduce the issue's stated approximately `900 ms` timing. This
revision flags the mode on the fourth timed-out request, and accepted
process-stop fallback installation occurs `1086.042–1364.638 ms` after fault.
The current schema already contains `SetpointConfig.timeout_ms`, but the field
is behaviorally inert here and the library sends zero. The F4 differential
also confirms that keeping the health path alive prevents automatic fallback
through the complete bounded window while stale Rate influence continues.

The single F1 post-fallback stale-subject Route violation is additional to the
issue's qualitative pre-revocation policy-gap claim. It must be investigated or
reproduced under a new authorization before making a frequency, root-cause, or
upstream-fix claim.

## 10. Final Gate and limitations

The machine-readable Gate is
[`freshness_pilot_gate.json`](../../experiments/motivation/freshness/freshness_pilot_gate.json).
The immutable design and source basis are
[`SETPOINT_FRESHNESS_SOURCE_AUDIT.md`](SETPOINT_FRESHNESS_SOURCE_AUDIT.md) and
[`PRE_REVOCATION_FRESHNESS_ORACLE.md`](../design/PRE_REVOCATION_FRESHNESS_ORACLE.md).

Final disposition: `CURRENT_NATURAL_VIOLATION_FOUND`.

This disposition is bounded by four conditions:

1. F2 is measurement-insufficient at `1/3`; the complete planned matrix was not
   obtained and no extra attempt is authorized.
2. The natural Route violation occurred once and was not reproduced in this
   pilot.
3. Physical values apply only to the frozen SITL vehicle, setpoints, timing,
   and accepted initial-state windows.
4. The result authorizes no timeout fix, control-policy change, larger matrix,
   direct-actuator experiment, Family B work, Aerostack2 run, rapid-restart or
   concurrency study, or stateful fuzzing campaign.
