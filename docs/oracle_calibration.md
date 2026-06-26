# Property Oracle Calibration

Date: 2026-06-26

Scope: Tier 0 calibration for `scripts/property_oracle.py`, using existing nominal no-disturbance SIH ULOGs under `docs/mcnn_gonogo_gate3_20260625/evals/*baseline_s2026130{1..5}/`.

## Data

Nominal baseline set:

- 5 seeds: `20261301` through `20261305`
- controllers: `classical`, `mcnn`
- total ULOGs used: 10
- task: hover after the same classical approach and optional mode-23 `mc_nn` switch

Mode-23 identity was positively checked on the mcnn baseline logs: `neural_control` ran at 230-234 Hz, `raptor_input` was absent, and seed `20261301` had 6343 exact timestamp samples where `neural_control.network_output` equaled `actuator_motors.control[0..3]`.

## Thresholds

| parameter | value | basis |
|---|---:|---|
| `theta_max` | 90 deg | Catastrophic envelope from oracle design; nominal max tilt floor was 7.51 deg. |
| `tau_rec` | 1.5 s | Oracle design start value in the 1-2 s recovery band. |
| `omega_max` | 8.0 rad/s | Nominal smoothed max was 2.18 rad/s; factor 3.68. |
| `u_sat` | 0.99 | High motor saturation level from FUZZ severity evidence. |
| `epsilon_sat` | 0.01 | Gives all-motor high-saturation level 0.98. |
| `W_sat` | 0.5 s | Sustained loss-of-authority window; nominal all-motor high-sat run was 0.0 s. |
| `delta_u_max` | 0.70 | Nominal max smoothed adjacent motor jump was 0.230; factor 3.05. |
| `epsilon_set` | 1.75 m | Nominal tracking RMS max was 0.542 m; factor 3.23. |
| `T_set` | 8.0 s | Task-level settling allowance for post-command hover recovery. |
| `W_hold` | 2.0 s | Hold window for P5 settling. |
| `s_min` | 0.5 m | Minimum setpoint change treated as a step. |
| `A_max` | 18 deg | Nominal steady tilt peak-to-peak max was 5.42 deg; factor 3.32. |
| `W_osc` | 2.0 s | Oscillation window for P6. |
| `epsilon_ss` | 1.80 m | Nominal tracking RMS max 0.542 m gives factor 3.32; also exceeds worst 2 s axis-mean steady offset 1.425 m. |
| `W_ss` | 2.0 s | Steady-state mean-error window for P7. |
| `margin_c` | 0.02 | Small positive classical margin for heterogeneous rho units. |

Implementation denoising constants:

- `state_moving_average_s = 0.10`
- `control_moving_average_s = 0.02`

## Nominal Margins

After calibration, all 10 nominal runs are `S0_clean_recovery`.

| property | min rho over 10 nominal ULOGs |
|---|---:|
| P1 | 1.5144759660 |
| P2 | 5.8237351098 |
| P3 | 0.5000000000 |
| P4 | 0.4702097654 |
| P5 | 1.7500000000 |
| P6 | 0.2194896065 |
| P7 | 0.3754140622 |

Noise/denoising check: raw-vs-smoothed nominal attitude and rate differences were small relative to final margins. The worst raw tilt max was 7.70 deg versus smoothed 7.51 deg, far below `theta_max=90 deg`; worst raw rate max was 2.28 rad/s versus smoothed 2.18 rad/s, leaving 5.82 rad/s P2 margin. Behavior-class margins after smoothing were also above the nominal floor: P4 margin 0.47 motor units, P6 margin 0.219 rad (12.58 deg), and P7 margin 0.375 m.

## Boundary

The hover baseline does not trigger P5's step antecedent, so P5 is calibrated from nominal tracking error floor plus task timing rather than a non-vacuous step-settling event. The first property campaign with explicit step commands should revisit `epsilon_set`, `T_set`, and `W_hold`.
