decision: BUG-FOUND (corner_r6_f045_w6_n_phase0: differential_primary_bug)
status: HISTORICAL_LEAD_SUPERSEDED_BY_FUZZ1B_FUZZ1C_DECONTAM

# FUZZ-1 mc_nn_control Violent Activation

This first kill remains useful as activation evidence, but its original
differential-primary classification is not the current Route-A decision. The
matched-state FUZZ-1b run downgraded this exact lead, and FUZZ-1c decontam is
the final Route-A result.

run_id: `fuzz1_activation_20260625`
scope: offboard aggressive circle approach + SIH wind + mode 23 mc_nn activation + post-switch hover
mcnn_evals: 3
mcnn_hits: 3
max_pre_switch_roll_pitch_deg: 59.97890104232152
max_pre_switch_angular_rate_rad_s: 2.681960951696999

## Detection Discipline

The detector is mc_nn-first. Classical is run only after mc_nn detector hits and is used as a post-hoc classifier, not as a pre-filter. Pure tracking lag is ignored as a finding.

## Evals

| idx | controller | case | seed | stage | hit | severity | pre roll deg | pre rate rad/s | reasons | attribution |
|---:|---|---|---:|---|---|---:|---:|---:|---|---|
| 1 | mcnn | corner_r6_f045_w6_n_phase0 | 20261500 | phase1_extreme_corner | true | 3 | 50.4036077632262 | 2.601540069336632 | angular_rate_loss_of_control,attitude_loss_of_control,ground_contact_post_switch,motor_saturation | differential_primary_bug |
| 2 | classical | corner_r6_f045_w6_n_phase0 | 20261500 | phase1_extreme_corner | false | 0 | 51.82403542823137 | 0.6511456607011202 | - | - |
| 3 | mcnn | corner_r6_f045_w6_n_phase0_confirm1 | 20261601 | phase1_extreme_corner | true | 3 | 59.97890104232152 | 2.681960951696999 | angular_rate_loss_of_control,attitude_loss_of_control,ground_contact_post_switch,motor_saturation | differential_primary_bug |
| 4 | classical | corner_r6_f045_w6_n_phase0_confirm1 | 20261601 | phase1_extreme_corner | false | 0 | 51.851450791438005 | 0.6811377517999989 | - | - |
| 5 | mcnn | corner_r6_f045_w6_n_phase0_confirm2 | 20261602 | phase1_extreme_corner | true | 3 | 57.2513407796724 | 2.5693672886459145 | angular_rate_loss_of_control,attitude_loss_of_control,ground_contact_post_switch,motor_saturation | differential_primary_bug |
| 6 | classical | corner_r6_f045_w6_n_phase0_confirm2 | 20261602 | phase1_extreme_corner | false | 0 | 49.806756167654136 | 0.6889470826892085 | - | - |

## Confirmed Bug

case: `corner_r6_f045_w6_n_phase0`
classification: differential_primary_bug
seeds: [20261500, 20261601, 20261602]
mcnn_hit_count: 3
primary_count: 3
reachability: Classical Offboard circle approach, wind_n=6.0, wind_e=0.0, setup_profile=relaxed_limits; relaxed limits are IC setup only.

### Source Trace

The hit is flight-dynamic; source attribution is through mode-23 mc_nn activation versus matched classical rerun.

## Validity Checks

- True failure, not harness: all 6 confirmation runs have `run_error=null`; PX4 console fault scan is false; task nodes reached `mission_end`. The mc_nn failure is flight-dynamic loss of control, not a timeout/crash artifact.
- Multi-seed reproduction: 3/3 mc_nn seeds hit; 3/3 matched classical reruns stayed flight-safe under the wide detector.
- Numerical/software channel: `neural_control.network_output` nonfinite count is 0/0/0 and active `actuator_motors.control[0..3]` nonfinite count is 0/0/0. No assert/crash/NaN was found in this first kill.
- mc_nn post-switch outcome: roll/pitch reached 179.97-180.00 deg, angular rate reached 24.44-24.84 rad/s, min altitude AGL reached -2.31 to -1.69 m, and active motor saturation ratio was 0.993-0.997.
- Classical post-switch outcome: no detector hit; post-switch roll/pitch stayed at 49.42-51.49 deg, angular rate at 1.19-1.28 rad/s, min altitude AGL stayed above 2.09 m, and active motor saturation ratio stayed 0.000-0.002 in the detector window.
- Reachability: the IC was created by classical Offboard circle approach with SIH wind north=6 m/s and `setup_profile=relaxed_limits` (`MPC_TILTMAX_AIR=89`, high accel/jerk/rate limits). This is explicitly IC setup, not a claim that default PX4 reaches this envelope.
- Realized switch states are recorded per run. mc_nn seeds entered mode 23 at roll/pitch 50.4/60.0/57.3 deg and angular rate 2.60/2.68/2.57 rad/s. Matched classical reruns used the same theta/seed/disturbance and reached similar roll/pitch 51.8/51.9/49.8 deg at the switch window, but lower angular rate 0.65/0.68/0.69 rad/s; this caveat should be reported with the finding.
