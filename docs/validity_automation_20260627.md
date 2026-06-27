# Tier 1 Validity Automation

Date: 2026-06-27

Scope: Tier 1 §3.4 only. No campaign orchestration, no resume work, no baseline,
and no Step C throughput decision.

## Code Changes

- Added `scripts/validity_automation.py` for shared validity gates:
  symmetric FUZZ-1c-style decontamination, mc_nn identity gate, and rho jitter
  reproduction margins.
- `scripts/property_oracle.py` now computes all P1-P7 rho values on the
  decontaminated control window and writes the full decontamination record under
  `window.decontamination`.
- `scripts/property_oracle.py` now records strict mode-23 identity evidence under
  `controller_identity.identity_gate`.
- `scripts/property_fitness.py` now separates:
  `candidate_differential_properties` (`rho_neural <= 0`) from
  `clean_differential_properties` (`rho_neural <= -repro_margin[P]`).
- `scripts/m2_map_elites.py` now fail-loud excludes evals that fail
  decontamination or identity gates, writes validity JSON per eval, records
  `(theta, seed) -> ulog` mappings in `progress.jsonl` and `EvalResult.evidence`,
  and requires confirmation repeats to reproduce the same robust property.

## Symmetric Decontamination

Rule reused from FUZZ-1c: for both controllers, a terminal event is
infrastructure/setup contamination only when `vehicle_status.failsafe` or an
RTL/land nav-state exit has a near-edge infrastructure cause in
`failsafe_flags`. Ground contact after that infrastructure terminal is treated
as aftermath. Rho is computed from analysis start to the first infrastructure
terminal; unresolved failsafe or start below 1.0 m AGL is fail-loud invalid.

Route-A replay on existing FUZZ-1c ULOGs, using explicit switch-to-mission
windows:

| pair | case | classical terminal | classical control s | classical severity | mc_nn terminal | mc_nn severity | strict |
|---:|---|---|---:|---|---|---|---|
| 1 | `rp48_62_rate2p45_2p90_w6_r6_f045` | INFRASTRUCTURE | 50.444 | S0 | NONE | S3 | true |
| 2 | `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` | INFRASTRUCTURE | 49.420 | S0 | NONE | S3 | true |
| 4 | `rp36_44_rate1p55_2p15_w3_r4_f038` | INFRASTRUCTURE | 51.000 | S0 | NONE | S3 | true |
| 5 | `rp32_40_rate1p30_1p95_w0_r4_f038` | INFRASTRUCTURE | 51.592 | S0 | NONE | S3 | true |

Result: all four remain strict S0-vs-S3 after automated decontamination, matching
`docs/fuzz1c_decontam_20260625.md`.

## Identity Gate

Hard gate for real mode-23 evals:

- `neural_control` rate in 200-280 Hz.
- `raptor_input` absent.
- At least 1000 exact timestamp samples where
  `neural_control.network_output[0..3] == actuator_motors.control[0..3]`.
- Exact-match fraction at least 0.80.

Offline pass sample:

- ULOG: `docs/parallel_profile_smoke/evals/smoke/docs/mcnn_gate3_parallel_profile_smoke_mcnn.ulg`
- Gate: passed.
- Evidence: 229.526 Hz, 6202 exact-equal samples, 0.9058 exact-match fraction,
  `raptor_input_present=false`.

Offline fail-loud sample:

- Classical ULOG checked as mcnn identity.
- Gate: failed with
  `insufficient_neural_control_samples`,
  `neural_control_rate_outside_expected_mode23_band`,
  `network_output_not_actuator_motors`, and
  `network_output_actuator_match_fraction_low`.

`m2_map_elites.evaluate_theta()` fail-loud probe:

- Forced the mcnn branch identity gate to fail after normal property evaluation.
- Result: `returncode=2`, `primary_bug=false`, fitness floor, error
  `validity_gate_failed: mcnn_identity:forced_identity_fail_for_probe`, and both
  ULOG paths retained in `evidence.ulog_paths`.

## Jitter Margins

Intrinsic rho jitter bands come from fixed-theta serial repeats in
`docs/parallel_profile_20260626.md` and the corresponding property JSONs. The
reproduction margin is `max(0.02, 2.0 * jitter_band)`.

| property | serial rho jitter band | reproduction margin |
|---|---:|---:|
| P1 | 0.0127931677 | 0.0255863354 |
| P2 | 0.0935180205 | 0.1870360410 |
| P3 | 0.0000000000 | 0.0200000000 |
| P4 | 0.0142966629 | 0.0285933258 |
| P5 | 0.2834851297 | 0.5669702594 |
| P6 | 0.0136974981 | 0.0273949962 |
| P7 | 0.2242437213 | 0.4484874426 |

Consequence: a P7 edge case such as `rho_neural=-0.05` is recorded as a
candidate differential but not a finding. A P7 finding must have
`rho_neural <= -0.4484874426` and pass the classical margin, then reproduce
across confirmation seeds on the same property.

## Pipeline Check

Mock structural run:

- Command used `--mock-evaluator --budget 3 --confirm-repeats 2`.
- Confirmation recorded `required_properties` and per-repeat
  `confirmation_repeated_properties`; one mock P7 candidate passed because every
  repeat reproduced P7 beyond the P7 margin.

Real small run:

- Command used container entrypoint, N=1, `--budget 2`, `--subspace
  steady-wind-physics`, `--target-properties behavior`, `--sim-speed-factor
  1.25`, `--no-confirm`.
- Run dir: `docs/validity_automation_real_20260627` (generated artifact, not to
  commit).
- 2/2 evals completed with `error=null`; no candidate finding.
- `progress.jsonl` contains `theta_ulog_map` for both evals.
- Eval 0 identity: 230.458 Hz, 6043 exact-equal samples, 0.8949 fraction,
  `raptor_input_present=false`; decontamination passed for both controllers.
- Eval 1 identity: 230.065 Hz, 6263 exact-equal samples, 0.9101 fraction,
  `raptor_input_present=false`; decontamination passed for both controllers.

## Verification

- `python3 -m unittest tests/test_property_fitness.py tests/test_theta_genome.py tests/test_validity_automation.py`
- `python3 -m py_compile scripts/validity_automation.py scripts/property_oracle.py scripts/property_fitness.py scripts/m1_compare.py scripts/m2_map_elites.py tests/test_validity_automation.py tests/test_property_fitness.py`
- Route-A ULOG replay: 4/4 strict S0-vs-S3 after automated decontamination.
- Identity pass/fail-loud offline probes passed.
- Real two-eval small run passed all validity gates and wrote evidence mappings.
