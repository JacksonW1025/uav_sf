decision: CLEAN_DIFFERENTIAL

# FUZZ-1c Severity Scan

run_id: `fuzz1c_severity_20260625`
method: Method A, SIH groundtruth state-triggered switch
state_shim: not used

## Decision

Found matched-state severity differential: classical severity S2_controlled_safe_failure and mc_nn severity S3_uncontrolled_tumble_or_loc.

## Interpretation

This is a wide-clean differential: classical is controlled S2 while mc_nn is uncontrolled S3. No strict classical S0/S1 vs mc_nn S3 point was found in this scan.

Observed S2-vs-S3 band: mc_nn S3 switch states span 39.67-48.80 deg and 1.82-2.75 rad/s.
Low-severity coverage reached mc_nn S0 at 16.39 deg / 0.48 rad/s and included valid matched points below 25-30 deg.
One no-wind low bucket is explicitly UNTESTED because the approach never entered its 22-32 deg trigger window; it is not used as no-hit evidence.

## Severity Ladder

- S0: clean recovery; final hover error, attitude, rate, and altitude back inside the S0 thresholds.
- S1: controlled degraded survival; no failsafe/ground/tumble, but not clean S0.
- S2: controlled safe failure; bounded attitude/rate but failsafe, disarm, or ground contact.
- S3: uncontrolled loss of control; roll/pitch >= 90 deg or angular-rate norm >= 8 rad/s.
- S4: numerical/software fault; console fault or active nonfinite controller/motor output.

thresholds_json: `fuzz1c_severity_20260625/severity_thresholds.json`

## Pairs

| idx | case | valid | mc_nn switch rp/rate | classical switch rp/rate | residual rp/rate | mc_nn severity | classical severity | differential | reasons |
|---:|---|---|---:|---:|---:|---|---|---|---|
| 1 | rp48_62_rate2p45_2p90_w6_r6_f045 | true | 48.23/2.60 | 48.85/2.63 | 0.62/0.03 | S3_uncontrolled_tumble_or_loc | S2_controlled_safe_failure | S2-vs-S3 | mc_nn=angular_rate_loss_of_control,attitude_tumble_over_90deg; classical=failsafe,ground_contact_post_switch |
| 2 | rp48_62_rate2p45_2p90_w6_r6_f045_confirm1 | true | 48.80/2.75 | 48.30/2.72 | 0.50/0.03 | S3_uncontrolled_tumble_or_loc | S2_controlled_safe_failure | S2-vs-S3 | mc_nn=angular_rate_loss_of_control,attitude_tumble_over_90deg; classical=failsafe,ground_contact_post_switch |
| 3 | rp40_48_rate2p00_2p55_w0_r6_f045 | true | 47.46/2.07 | 47.03/2.25 | 0.43/0.18 | S0_clean_recovery | S2_controlled_safe_failure | - | mc_nn=; classical=failsafe,ground_contact_post_switch |
| 4 | rp36_44_rate1p55_2p15_w3_r4_f038 | true | 40.81/1.95 | 39.59/1.96 | 1.22/0.01 | S3_uncontrolled_tumble_or_loc | S2_controlled_safe_failure | S2-vs-S3 | mc_nn=angular_rate_loss_of_control,attitude_tumble_over_90deg; classical=failsafe,ground_contact_post_switch |
| 5 | rp32_40_rate1p30_1p95_w0_r4_f038 | true | 39.67/1.82 | 39.00/1.94 | 0.67/0.12 | S3_uncontrolled_tumble_or_loc | S2_controlled_safe_failure | S2-vs-S3 | mc_nn=angular_rate_loss_of_control,attitude_tumble_over_90deg; classical=failsafe,ground_contact_post_switch |
| 6 | rp25_34_rate0p80_1p45_w3_r2p5_f032 | true | 31.52/1.42 | 33.87/1.22 | 2.35/0.19 | S0_clean_recovery | S2_controlled_safe_failure | - | mc_nn=; classical=failsafe,ground_contact_post_switch |
| 7 | rp22_32_rate0p55_1p30_w0_r2p5_f032 | false | -/- | -/- | -/- | UNTESTED_TRIGGER_NOT_FIRED | UNTESTED_TRIGGER_NOT_FIRED | - | mc_nn=state_trigger_not_fired; classical=state_trigger_not_fired |
| 8 | rp18_30_rate0p40_1p20_w3_r1p8_f025 | true | 19.17/0.65 | 18.65/0.49 | 0.52/0.16 | S0_clean_recovery | S2_controlled_safe_failure | - | mc_nn=; classical=failsafe,ground_contact_post_switch |
| 9 | rp12_28_rate0p25_1p00_w0_r1p8_f025 | true | 16.39/0.48 | 16.56/0.47 | 0.17/0.01 | S0_clean_recovery | S2_controlled_safe_failure | - | mc_nn=; classical=failsafe,ground_contact_post_switch |

## Coverage

{
  "max_valid_mcnn_roll_pitch_abs_deg": 48.79882246369493,
  "min_valid_mcnn_roll_pitch_abs_deg": 16.394111386186104,
  "pair_count": 9,
  "rate_residual_mean_rad_s": 0.09130438299991246,
  "s2_vs_s3_count": 4,
  "strict_clean_differential_count": 0,
  "untested_count": 1,
  "valid_pair_count": 8,
  "wide_clean_differential_count": 4
}

## Validity

Trigger timeouts are marked UNTESTED and are not used as safe/no-hit evidence. ULOG switch states are matched back to groundtruth by value, and the Method-A residual is reported per pair.

## Artifacts

results_json: `fuzz1c_severity_20260625/results.json`
results_jsonl: `fuzz1c_severity_20260625/results.jsonl`
eval_dir: `fuzz1c_severity_20260625/evals`
