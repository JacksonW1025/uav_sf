# Wave-2 Gate A Diagnostic

Date: 2026-07-03

Status: diagnostic only. No gate change, no shim edit, no Step C, and no wave-2 campaign.

## Question

Gate A rebuilt the M2B state shim with a new `M2B_P_*` position channel. The
deep anchors pair1/pair2 stayed strict, but boundary anchors pair4/pair5 failed
the single-sample Gate A rerun:

| anchor | case | Gate A rebuilt-shim result |
|---|---|---|
| pair4 | `rp36_44_rate1p55_2p15_w3_r4_f038` | classical S0, mc_nn S1 |
| pair5 | `rp32_40_rate1p30_1p95_w0_r4_f038` | classical S0, mc_nn S0 |

The diagnostic question is H1 boundary randomness vs H2 zero-contamination shim
side effect.

## Structural Check

Source inspected in `external/PX4-Autopilot` and matching tracked patch
`patches/px4/m2b_state_shim.patch`.

Findings:

- Parameter defaults are off/zero: `M2B_EN` defaults `false`; `M2B_P_PROF`,
  `M2B_V_PROF`, and `M2B_G_PROF` default `0`; position/velocity/angular-rate
  amplitudes default `0.0`.
- Direct publication-field no-op under default zero contamination: the position,
  velocity, attitude, and angular-rate hooks all return before injection
  branches when `M2B_EN=false`.
- Not a strict whole-function/whole-timing no-op: each hook writes its private
  ring buffer and advances an index before the `M2B_EN` guard. The new position
  path therefore adds always-on work at local-position publication time even
  when output fields are unchanged.
- EKF2 position `param_find`/`param_get` path is not hot in default zero
  contamination: `UpdateM2BPositionShimParams()` is called only after
  `m2bShimActive(...)` passes. With current params present, `param_find` is
  guarded by `_m2b_p_prof_handle == PARAM_INVALID` and becomes one-time per EKF2
  object when active. No uninitialized read was found; cached values initialize
  to zero.

Conclusion: no direct zero-parameter output mutation was found, and the special
EKF2 position param path does not explain Gate A in the disabled/default case.
There is a structural no-op caveat: the shim is not bit/no-timing no-op because
buffer writes happen before the guard. This is a cleanliness issue to consider
later, but by itself it predicts a tiny common timing/layout perturbation, not a
stable boundary-lowering failure.

## Behavior Diagnostic

Command driver:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=wave2_gateA_diag_multiseed ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python3 runs/route_a_anchor_regression/wave2_gateA_diag_multiseed_20260703/diag_driver.py"'
```

Artifact:
`runs/route_a_anchor_regression/wave2_gateA_diag_multiseed_20260703/diagnostic_results.json`

Current rebuilt shim, zero contamination/default M2B params:

| anchor | seeds | valid | strict S0/S3 | hit rate | non-strict seeds |
|---|---:|---:|---:|---:|---|
| pair4 | `20261802..20262502` | 8/8 | 7/8 | 87.5% | `20262202` = S0/S0 |
| pair5 | `20261803..20262503` | 8/8 | 8/8 | 100.0% | none |

Per-seed notes:

- pair4 historical baseline seeds `20261802`, `20261902`, `20262002` remain
  3/3 strict on the rebuilt shim.
- pair4 Gate A same seed `20261802` was S1, but this diagnostic rerun returned
  S3.
- pair5 same seed `20261803` was S0 in the pre-position baseline and in Gate A,
  but this diagnostic rerun returned S3.
- All current non-strict/strict changes are on the mc_nn side; classical stayed
  S0 for all 16 current pair4/pair5 paired evals.

Baseline comparison used existing pre-position-channel artifacts, not a fresh
shim-free rebuild:

| anchor | baseline artifact | baseline strict rate | comparable current rate |
|---|---|---:|---:|
| pair4 | `route_a_addendum3_diag_20260629` | 3/3 | same 3 seeds: 3/3; expanded 8 seeds: 7/8 |
| pair5 | `route_a_addendum3_diag_20260629` | 8/9 | same first 8 seeds: 8/8 |

This is a strong practical baseline for pair5 and a partial baseline for pair4.
It is not the strongest possible same-8-seed clean-control baseline because no
fresh pre-position/shim-free binary was rebuilt in this diagnostic.

## Interpretation

The data support H1 overall.

- The failed Gate A points are exactly the known onset/below-onset boundary
  points; deep pair1/pair2 stayed strict in Gate A.
- Multi-seed rebuilt-shim rates are high and consistent with the historical
  probabilistic boundary story: pair4 7/8, pair5 8/8, versus historical pair4
  3/3 and pair5 8/9.
- Same-seed outcomes flip across reruns at the boundary. In particular,
  pair5 `20261803` changed S0 -> S3 without changing shim code between the Gate
  A run and this diagnostic rerun. That is direct evidence against treating
  pair5 as a deterministic single-sample gate.
- No structural evidence was found for a zero-parameter position-param read bug
  or direct output-field mutation.

H2 is not supported as a behavior-changing zero-contamination shim bug. The
remaining H2-compatible caveat is only that the shim has always-on buffer writes
before the guard, including the new position buffer. If humans want stricter
cleanliness later, that can be hardened, but the observed regression pattern and
multi-seed rates do not show a stable shim-induced boundary movement.

## Gate Recommendation For Human Decision

Do not use pair4/pair5 as single-run hard anchors.

Suggested Gate A shape:

- hard gate: deep/deterministic anchors pair1 and pair2 must remain strict
  S0/S3;
- probabilistic tracking gate: boundary anchors pair4/pair5 must be evaluated
  over a fixed seed set and compared to historical rates with tolerance, e.g.
  a `>=2/3` or `>=6/8` strict-rate floor plus per-seed table reporting;
- report boundary flips explicitly instead of treating one S0/S1 sample as a
  shim failure.

Gate/shim decision remains with humans.
