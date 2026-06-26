decision: DOWNGRADED

# FUZZ-1b Locked Differential

Status note: this downgrade remains important as the state-alignment lesson, but it is superseded as the final Route-A decision by `fuzz1c_severity_20260625.md` and `fuzz1c_decontam_20260625.md`.

run_id: `fuzz1b_locked_20260625`

## Decision

FUZZ-1's violent-activation lead is downgraded as a differential primary bug.

With state-triggered switching on SIH groundtruth, the original target region was aligned tightly: mc_nn switched at 48.40 deg / 2.67 rad/s and classical at 48.65 deg / 2.77 rad/s. From that matched state, mc_nn still lost control, but classical also hit the wide flight-unsafe detector (`failsafe`, `ground_contact_post_switch`). This makes the original FUZZ-1 point too-hard rather than NN-specific.

A bounded severity-down scan found no `classical safe && mc_nn unsafe` point. In all five valid matched pairs down to about 41.5 deg / 1.49 rad/s, both controllers failed the detector. The last easy bucket was harness-limited on the mc_nn branch because the trigger did not fire before deadline and PX4 outlived the harness wait; it is not used as a no-hit result.

## Method

SIH state-control probe: `simulator_sih` has no built-in snapshot/restore/direct-state API for full dynamics state. Its true state is private module state, and `sih_params.yaml` exposes physical parameters and wind/origin, not initial attitude/rate/velocity. Method A was used.

To make Method A use true SIH state instead of estimator-only topics, FUZZ-1b adds DDS publications for `vehicle_attitude_groundtruth`, `vehicle_angular_velocity_groundtruth`, and `vehicle_local_position_groundtruth` in the mc_nn SIH build. The task node triggers on groundtruth threshold crossing, then the runner matches the trigger state back to ULOG groundtruth by value to get the exact boot-time switch sample.

## Scan Results

| case | mc_nn switch rp/rate | classical switch rp/rate | max residual rp/rate | mc_nn outcome | classical outcome | class |
|---|---:|---:|---:|---|---|---|
| target 2.45-2.85 | 48.40 deg / 2.67 | 48.65 deg / 2.77 | 0.25 deg / 0.10 | LOC + ground | failsafe + ground | too-hard |
| scan 2.20-2.60 | 45.39 deg / 2.39 | 45.19 deg / 2.21 | 0.20 deg / 0.18 | LOC + ground | failsafe + ground | too-hard |
| scan 1.80-2.30 | 46.92 deg / 2.28 | 45.07 deg / 2.30 | 1.84 deg / 0.01 | LOC + ground | failsafe + ground | too-hard |
| scan 1.40-1.90 | 42.17 deg / 1.83 | 45.32 deg / 1.88 | 3.15 deg / 0.05 | LOC + ground | failsafe + ground | too-hard |
| scan 1.00-1.50 | 41.73 deg / 1.50 | 41.53 deg / 1.49 | 0.20 deg / 0.01 | LOC + ground | failsafe + ground | too-hard |

Across valid matched pairs, max switch residuals were 3.15 deg roll/pitch, 0.179 rad/s angular-rate norm, and 0.58 m/s velocity norm. ULOG trigger matching was exact for all but one classical pair, where angular-rate match error was 0.029 rad/s.

## Validity

The first five matched pairs had `run_error=null`, no PX4 console assert/fault match, and ULOGs were copied and analyzed. The failure mode is flight-dynamic, not NaN/assert/crash: mc_nn repeatedly reached about 180 deg roll/pitch and 24.2-24.7 rad/s after switch; classical did not tumble but still descended through ground and entered failsafe under the same matched handoff family.

The easy 0.65-1.10 rad/s bucket is excluded from the differential decision. Its mc_nn task timed out waiting for the trigger; no matched mc_nn switch state exists for that bucket.

## Reachability

The tested states were reached by classical Offboard circle approach with SIH wind and relaxed IC-setup limits (`MPC_TILTMAX_AIR=89`, high accel/jerk/rate limits). This does not claim default PX4 position-control envelope reaches the state. The honest framing remains dynamic handoff/upset recovery: if the aircraft is already in this aggressive state, both controllers are compared from a matched true-state trigger.

## Exit

FUZZ-1's first-kill remains a real mc_nn activation loss-of-control, but its differential claim is not confirmed. For this offboard+wind activation family, the matched-state evidence says the lead is too-hard. Next decision should come from the user: either patch SIH for direct state ICs to decouple reachability/altitude/speed more cleanly, or move to the next mechanism family such as velocity/angular-rate belief injection after the shim drift is repaired.
