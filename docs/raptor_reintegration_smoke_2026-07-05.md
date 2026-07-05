# RAPTOR Reintegration Smoke, 2026-07-05

## Scope

This was a reintegration plus smoke pass for original RAPTOR, keeping its
position and velocity error clipping unchanged. It did not run a full route-A
campaign, RQ2/RQ3, Step C, or an unclipped RAPTOR variant.

## Integration

The campaign harness now has a SUT selector for `mcnn` and `raptor`. The
default remains `mcnn`. For `raptor`, the evaluator dispatches through the
RAPTOR runner, stages `policy.tar`, records RAPTOR-specific metadata, writes
RAPTOR property files, and uses the RAPTOR identity gate. The differential
fitness semantics are unchanged: classical rho minus neural rho, with neural
set to the selected SUT.

Board decision: use `raptor_sih` and add the same DDS groundtruth installer
used by the mc_nn board. This keeps the smoke isolated to `MC_RAPTOR` and
avoids a board with both `MC_RAPTOR` and `MC_NN_CONTROL` enabled. Static sanity
checked that `raptor_sih` enables `CONFIG_MODULES_MC_RAPTOR=y`, does not enable
`CONFIG_MODULES_MC_NN_CONTROL=y`, and that
`scripts/build_px4_raptor_sih.sh` installs the DDS groundtruth topics.

The local ROS overlay had stale Python 3.12 `px4_msgs` artifacts. The smoke
environment was rebuilt locally for Python 3.10/Humble so `RaptorStatus` and
`RaptorInput` type support could load. Generated ROS build artifacts remain
untracked.

## Identity Gate

`raptor_identity_gate()` requires:

- `controller == "raptor"`
- `raptor_status` present and active in the control window
- `raptor_input` present with active samples in the control window
- target nav state 23 with sufficient fraction in the control window
- no `neural_control` topic
- `policy.tar` staged

The real smoke ULOGs passed this gate in all 8 evaluations. Active
`raptor_status` samples ranged from 9864 to 10247, `raptor_input` samples from
10930 to 11333, and target nav-state fraction from 0.8969 to 0.9000.

## Smoke Results

Run artifacts are under `runs/raptor_reintegration_smoke_20260705/`. They are
not part of the commit.

| anchor | seed | case | wind | classical S | RAPTOR S | identity | decontam | `m1_compare` P1-P7 |
|---|---:|---|---|---:|---:|---|---|---|
| pair1 | 20261800 | `rp48_62_rate2p45_2p90_w6_r6_f045` | N=6,E=0 | 0 | 0 | pass | pass | pass |
| pair2 | 20261901 | `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` | N=6,E=0 | 0 | 1 | pass | pass | pass |
| pair4 | 20261802 | `rp36_44_rate1p55_2p15_w3_r4_f038` | N=3,E=0 | 0 | 0 | pass | pass | pass |
| pair5 | 20261803 | `rp32_40_rate1p30_1p95_w0_r4_f038` | N=0,E=0 | 0 | 0 | pass | pass | pass |
| pair1 | 20262001 | `rp48_62_rate2p45_2p90_w6_r6_f045` | N=6,E=0 | 0 | 0 | pass | pass | pass |
| pair2 | 20262101 | `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` | N=6,E=0 | 0 | 0 | pass | pass | pass |
| pair4 | 20261902 | `rp36_44_rate1p55_2p15_w3_r4_f038` | N=3,E=0 | 0 | 0 | pass | pass | pass |
| pair5 | 20261903 | `rp32_40_rate1p30_1p95_w0_r4_f038` | N=0,E=0 | 0 | 0 | pass | pass | pass |

RAPTOR mostly held the route-A anchor states in this smoke. The only non-S0
RAPTOR outcome was pair2 seed 20261901 at S1. No smoke result was a strict
S0-vs-S3 differential against RAPTOR.

## Comparability Checks

| criterion | result |
|---|---|
| RAPTOR identity real ULOG check | pass, 8/8 |
| Decontaminated control-window cut and severity recompute | pass, 8/8 for both classical and RAPTOR |
| Differential shell | pass, `m1_compare.py --neural-controller raptor` produced P1-P7 per-property output for 8/8 |
| Classical side consistency | pass, RAPTOR smoke classical side was S0 in 8/8; existing mc_nn anchor artifacts also mark the matching route-A classical cases as `S0_clean_recovery_decontaminated` |
| Validity health | pass, no identity, staging, decontam, or invalid-result collapse after the ROS overlay was rebuilt |

Classical consistency sources include
`runs/route_a_anchor_regression/wave2_gateA_prime_20260703/gate_a_prime_results.json`,
`runs/route_a_anchor_regression/route_a_addendum3_diag_20260629/diagnostic_results.json`,
and
`runs/route_a_anchor_regression/wave2_gateA_diag_multiseed_20260703/diagnostic_results.json`.

## Conclusion

Original clipped RAPTOR is now a complete, mc_nn-comparable SUT in the current
campaign harness at smoke scale. It is ready for a separate full route-A
campaign decision. This result does not answer whether clipping is the main
source of RAPTOR robustness.

## Caveats

- RAPTOR input clipping was preserved.
- This was smoke only: 4 anchors, 2 seeds each, serial N=1.
- No full campaign, RQ2/RQ3, Step C, or unclipped variant was run.
- The local ROS overlay rebuild was necessary because the previous
  `ros2_ws/install` had Python 3.12 artifacts while the active runtime is
  Python 3.10/Humble.
