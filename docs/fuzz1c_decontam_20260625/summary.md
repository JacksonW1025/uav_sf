decision: STRICT_DIFFERENTIAL_CONFIRMED

# FUZZ-1c Decontamination Rejudgment

source_run: `docs/fuzz1c_severity_20260625/results.json`
method: existing ULOG-only reanalysis; no reruns; shim not used

## Symmetric Decontamination Rule

The rule is applied identically to `classical` and `mc_nn`. A terminal event is infrastructure/setup contamination only when the ULOG shows an infrastructure failsafe trigger near `vehicle_status.failsafe`, or ground contact follows that infrastructure failsafe. Control-level severity is then judged only on the window before that terminal event. A true pre-terminal tumble or angular-rate loss remains S3.

Infrastructure trigger fields checked in `failsafe_flags`: `offboard_control_signal_lost`, `manual_control_signal_lost`, `gcs_connection_lost`, high-latency datalink loss, and estimator position/velocity/altitude invalid flags. For this run the causal near-edge field is `offboard_control_signal_lost`; baseline flags that are already true without a near failsafe edge are recorded but not treated as the cause.

## Decision

Strict differential confirmed: 4 matched states have control-level `classical=S0/S1` and `mc_nn=S3`.

## Severity-Invariance Diagnosis

Classical terminal events are severity-invariant: across valid pairs, switch severity spans 16.56-48.85 deg and 0.47-2.72 rad/s, but the first classical failsafe occurs at 73.944-78.272 s absolute and is classified as INFRASTRUCTURE.

The invariant terminal shape is `vehicle_status.failsafe` + nav-state exit from OFFBOARD to AUTO_RTL, `failsafe_flags.offboard_control_signal_lost` rising 0.012-0.012 s before `failsafe`, and then ground contact 6.82-9.42 s later. Touchdown is therefore treated as infrastructure-failsafe aftermath, not the control failure evidence.

Before that terminal event, classical is already recovered/stable: over the last 2 s before failsafe, max roll/pitch <= 17.31 deg, max angular rate <= 0.20 rad/s, last hover error <= 1.17 m, and min AGL >= 2.39 m.

Common active `failsafe_flags` at the classical failsafe sample: `auto_mission_missing, gcs_connection_lost, manual_control_signal_lost, offboard_control_signal_lost, remote_id_unhealthy`. Only `offboard_control_signal_lost` has a near-edge timing at the terminal event; the others are baseline environment flags and are retained as evidence, not used as the causal classifier.

## Pair Table

| idx | case | class switch rp/rate/AGL | class failsafe abs/dt | class pre-terminal rp/rate/err/AGL | class control sev | mc_nn control sev | decision |
|---:|---|---:|---:|---:|---|---|---|
| 1 | rp48_62_rate2p45_2p90_w6_r6_f045 | 48.85/2.63/2.76 | 75.176/50.44 | 17.29/0.16/0.48/2.49 | S0_clean_recovery_decontaminated | S3_control_loss_or_tumble | STRICT_DIFFERENTIAL |
| 2 | rp48_62_rate2p45_2p90_w6_r6_f045_confirm1 | 48.30/2.72/2.52 | 74.220/49.42 | 17.31/0.14/0.52/2.39 | S0_clean_recovery_decontaminated | S3_control_loss_or_tumble | STRICT_DIFFERENTIAL |
| 3 | rp40_48_rate2p00_2p55_w0_r6_f045 | 47.03/2.25/2.87 | 74.816/51.22 | 2.05/0.19/1.08/3.08 | S0_clean_recovery_decontaminated | S0_clean_recovery_decontaminated | NO_STRICT_DIFFERENTIAL |
| 4 | rp36_44_rate1p55_2p15_w3_r4_f038 | 39.59/1.96/2.54 | 74.236/51.00 | 8.95/0.19/0.45/2.44 | S0_clean_recovery_decontaminated | S3_control_loss_or_tumble | STRICT_DIFFERENTIAL |
| 5 | rp32_40_rate1p30_1p95_w0_r4_f038 | 39.00/1.94/2.81 | 74.848/51.59 | 1.61/0.20/1.04/2.89 | S0_clean_recovery_decontaminated | S3_control_loss_or_tumble | STRICT_DIFFERENTIAL |
| 6 | rp25_34_rate0p80_1p45_w3_r2p5_f032 | 33.87/1.22/2.08 | 73.944/41.32 | 9.22/0.14/0.37/2.52 | S0_clean_recovery_decontaminated | S0_clean_recovery_decontaminated | NO_STRICT_DIFFERENTIAL |
| 7 | rp22_32_rate0p55_1p30_w0_r2p5_f032 | - | - | - | skipped | skipped | SKIPPED_UNTESTED |
| 8 | rp18_30_rate0p40_1p20_w3_r1p8_f025 | 18.65/0.49/2.57 | 78.272/54.40 | 8.36/0.13/1.17/2.74 | S0_clean_recovery_decontaminated | S0_clean_recovery_decontaminated | NO_STRICT_DIFFERENTIAL |
| 9 | rp12_28_rate0p25_1p00_w0_r1p8_f025 | 16.56/0.47/2.58 | 78.264/54.42 | 2.02/0.18/0.24/2.67 | S0_clean_recovery_decontaminated | S0_clean_recovery_decontaminated | NO_STRICT_DIFFERENTIAL |

## Asymmetry Check

The same rule changes classical and does not rescue mc_nn because the data shapes differ. Classical S2 is caused by an infrastructure terminal event after stable controlled flight. The mc_nn S3 cases have no classified infrastructure terminal before the loss of control; their control window contains roll/pitch over 90 deg and angular rate over 8 rad/s, so they remain S3.

## Counts

```json
{
  "attitude_control_differential_count": 0,
  "skipped_untested_count": 1,
  "strict_differential_count": 4,
  "unresolved_count": 0,
  "valid_pairs": 8
}
```

## Artifacts

- structured results: `docs/fuzz1c_decontam_20260625/results.json`
- per-pair JSONL: `docs/fuzz1c_decontam_20260625/results.jsonl`
- criteria: `docs/fuzz1c_decontam_20260625/criteria.json`
