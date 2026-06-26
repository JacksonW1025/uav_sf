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
| `epsilon_set` | 1.05 m | P5 pure-step calibration: max best-`W_hold` max error was 0.339 m; factor 3.09 after rounding. |
| `T_set` | 5.0 s | P5 pure-step calibration: worst measured settling time was 3.88 s; +1.0 s slack rounded to 0.5 s. |
| `W_hold` | 2.0 s | Hold window for P5 settling. |
| `s_min` | 0.5 m | Minimum setpoint change treated as a step. |
| `A_max` | 18 deg | Nominal steady tilt peak-to-peak max was 5.42 deg; factor 3.32. |
| `W_osc` | 2.0 s | Oscillation window for P6. |
| `epsilon_ss` | 1.80 m | Nominal tracking RMS max 0.542 m gives factor 3.32; also exceeds worst 2 s axis-mean steady offset 1.425 m. |
| `W_ss` | 2.0 s | Steady-state mean-error window for P7. |
| `margin_c` | deprecated fallback only | Replaced by per-property `margin_c_Pi` below; the scalar is kept only for old JSON compatibility. |

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
| P5 | 1.0500000000 |
| P6 | 0.2194896065 |
| P7 | 0.3754140622 |

Noise/denoising check: raw-vs-smoothed nominal attitude and rate differences were small relative to final margins. The worst raw tilt max was 7.70 deg versus smoothed 7.51 deg, far below `theta_max=90 deg`; worst raw rate max was 2.28 rad/s versus smoothed 2.18 rad/s, leaving 5.82 rad/s P2 margin. Behavior-class margins after smoothing were also above the nominal floor: P4 margin 0.47 motor units, P6 margin 0.219 rad (12.58 deg), and P7 margin 0.375 m.

## Differential Classical Margins

`margin_c` is now per property. The old scalar `0.02` mixed radians, meters, seconds, and motor-command units, so it is retained only as a backward-compatible fallback field. Differential search and comparison use the `margin_c_Pi` values below.

For P1/P2/P3/P4/P6/P7, margins are 30% of the recomputed classical-only nominal minimum over the five `mcnn_gonogo_gate3_20260625` baseline classical ULOGs. P5 uses 30% of the non-vacuous pure-step classical minimum from `docs/tier05_p5_step_20260626/`.

| property | classical calibration source | classical min rho | `margin_c_Pi` |
|---|---|---:|---:|
| P1 | nominal classical hover, 5 seeds | 1.5160466486 | 0.4548139946 |
| P2 | nominal classical hover, 5 seeds | 7.8071126176 | 2.3421337853 |
| P3 | nominal classical hover, 5 seeds | 0.5000000000 | 0.1500000000 |
| P4 | nominal classical hover, 5 seeds | 0.6744345367 | 0.2023303610 |
| P5 | pure-step classical, 3 seeds | 0.3611290926 | 0.1083387278 |
| P6 | nominal classical hover, 5 seeds | 0.2530502121 | 0.0759150636 |
| P7 | nominal classical hover, 5 seeds | 0.3754140622 | 0.1126242187 |

Search validity is per property: a gap for `Pi` is counted only when `rho_i(classical) >= margin_c_Pi`. A failure by classical on another property does not invalidate a clean differential for `Pi`.

## P5 Step Calibration

The Tier 0 hover baseline still does not trigger P5's step antecedent, so its nominal P5 margin is vacuous and equals `epsilon_set`. Tier 0.5 added an explicit moderate step stimulus and calibrated P5 from non-vacuous pure-step SIH data:

- data: `docs/tier05_p5_step_20260626/`, 3 seeds (`20262601` through `20262603`) x 2 controllers (`classical`, `mcnn`)
- theta: pure 0.75 m x-axis setpoint step at 32 s, no wind, no physics mismatch, no shim
- rule: `epsilon_set = ceil_0.05(max(0.25, max best-W_hold max error * 3.0))`; `T_set = ceil_0.5(max measured settling time + 1.0 s)`; `W_hold = 2.0 s`
- calibrated values: `epsilon_set=1.05 m`, `T_set=5.0 s`, `W_hold=2.0 s`
- non-vacuous check: every run had exactly one detected P5 step and `details.P5.vacuous=false`
- calibrated P5 margins: classical min `0.3611290926`, mc_nn min `0.2998305995`; all six runs remained `S0_clean_recovery`
- mode-23 identity: mc_nn runs were confirmed at 229.2-230.7 Hz, `raptor_input` was absent, and `network_output` matched `actuator_motors` at exact timestamps.
