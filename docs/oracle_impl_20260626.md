# Property Oracle Tier 0 Implementation Report

Date: 2026-06-26

## Inventory

Existing ULOGs under `docs/*/evals/`: 75 `.ulg` files, all ignored by git.

Route A strict-differential anchors are present in `docs/fuzz1c_decontam_20260625/results.json`: pairs 1, 2, 4, and 5.

Self-check anchors:

- FUZZ-1 tumble: `docs/fuzz1_activation_20260625/evals/fuzz1_activation_20260625_corner_r6_f045_w6_n_phase0_s20261500/..._mcnn.ulg`
- nominal: `docs/mcnn_gonogo_gate3_20260625/evals/mcnn_gonogo_gate3_20260625_baseline_s20261301/..._mcnn.ulg`

`m1_metrics.py` convention reused: ULOG parsing via `pyulog`, task/nav-state window reconstruction, `trajectory_setpoint` as reference, and groundtruth topics preferred when present.

## 1.1 Property Oracle

Implemented `scripts/property_oracle.py` for P1-P7. It computes finite real robustness values, applies moving-average denoising, cuts control windows at classified infrastructure terminal events, maps properties to S0-S4, and records mcnn identity evidence.

Frame/unit conclusion in code: PX4 local position and setpoint are world NED meters; angular velocity is body-frame rad/s; attitude quaternion is Hamilton body-to-NED, with `tilt=acos(R33)`; active motor commands are `actuator_motors.control[0..3]`.

FUZZ-1 tumble rho:

| P | rho |
|---|---:|
| P1 | -0.0383916101 |
| P2 | -16.4178381324 |
| P3 | 0.5000000000 |
| P4 | 0.4549719810 |
| P5 | 1.7500000000 |
| P6 | -1.6765067370 |
| P7 | -26.2525873871 |

Result: `S3_uncontrolled_tumble_or_spin`; P1/P2 are both <= 0.

Nominal mcnn baseline rho:

| P | rho |
|---|---:|
| P1 | 1.5281266829 |
| P2 | 5.8268397637 |
| P3 | 0.5000000000 |
| P4 | 0.4730385303 |
| P5 | 1.7500000000 |
| P6 | 0.2483602080 |
| P7 | 0.8772575935 |

Result: `S0_clean_recovery`; all rho values are > 0.

## 1.4 Differential Wrapper

Extended `scripts/m1_compare.py` with optional property JSON/ULOG inputs. It now computes:

- per-property clean differential: `rho_neural <= 0 and rho_classical >= margin_c`
- S0-S4 severity from property results
- strict S0-vs-S3 and wider controlled-vs-uncontrolled flags

Route A strict anchors after calibrated thresholds:

| idx | case | classical | mc_nn | strict |
|---:|---|---|---|---|
| 1 | `rp48_62_rate2p45_2p90_w6_r6_f045` | S0 | S3 | true |
| 2 | `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` | S0 | S3 | true |
| 4 | `rp36_44_rate1p55_2p15_w3_r4_f038` | S0 | S3 | true |
| 5 | `rp32_40_rate1p30_1p95_w0_r4_f038` | S0 | S3 | true |

Honest boundary: these are catastrophic P1/P2-class validations. P6/P7 can also go negative after a tumble, but that is crash aftermath, not evidence that behavior-class P4-P7 differential power has been validated.

## 1.2 and 1.3 Calibration/Denoising

Calibration is in `docs/oracle_calibration.md`. All 16 required values are filled. Moving-average denoising is implemented centrally in `property_oracle.py` with 0.10 s state windows and 0.02 s control windows.

Nominal multi-seed result after calibration: 5/5 classical and 5/5 mcnn baseline runs are `S0_clean_recovery`. Minimum nominal margins are P1=1.5145, P2=5.8237, P3=0.5, P4=0.4702, P5=1.75, P6=0.2195, P7=0.3754.

Mode-23 controller ID on nominal mcnn baseline: 230-234 Hz `neural_control`, `raptor_input` absent, and thousands of exact timestamp equality samples between `network_output` and `actuator_motors.control[0..3]`.

## Final Recheck

After calibration, the Step 1 self-check and Step 2 Route A replay still hold:

- FUZZ-1 tumble: P1/P2 <= 0, severity S3.
- nominal baseline: all seven rho values > 0, severity S0.
- Route A 4 pairs: all `classical=S0` and `mc_nn=S3`.
