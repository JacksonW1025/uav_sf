# Wave-2 State-Contam Gate A Halt

Date: 2026-07-03

Status: **HALT at Phase A / Gate A**. Phase B/C/D were not entered and no
wave-2 campaign was run.

## Scope Executed

- Audited the dirty PX4 M2B state shim in `external/PX4-Autopilot`.
- Classified the existing shim as **half-complete** for wave-2: velocity and
  angular-rate injection paths existed, but `position_estimate_jump_m` had no
  position-output injection path.
- Mechanically added the missing position channel as `M2B_P_*`:
  - PX4 parameter definitions in `src/modules/mc_raptor/module.yaml`.
  - `vehicle_local_position.x/y/z` injection in `EKF2` and `EKF2Selector`.
  - `ApplyM2BPositionShim(...)` before the existing velocity shim at local
    position publish time.
- Regenerated `patches/px4/m2b_state_shim.patch`.
- Added a targeted patch-coverage test:
  `tests/test_m2b_state_shim_patch.py`.

Implementation note: `EKF2` was already close to the PX4
`DEFINE_PARAMETERS(...)` macro argument limit. Adding five `M2B_P_*` entries to
that macro caused compilation to fail, so the final fix reads the new position
params through private `param_find` / `param_get` handles in `EKF2`. The
selector path still uses the normal `DEFINE_PARAMETERS(...)` route because it is
well below the macro limit.

## Validation Before Anchor Regression

Passed:

- `python -m unittest tests.test_m2b_state_shim_patch -v`
- PX4 shim source `git diff --check`
- Root repo `git diff --check` for the touched tracked files
- Clean PX4 temporary worktree patch round-trip:
  - `git apply --check`
  - `git apply`
  - `git apply --reverse --check`
  - `git apply --reverse`
- PX4 board build:
  - `sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=wave2_gate_a_build ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && ./scripts/build_px4_mcnn_sih.sh"'`

Local environment note: `/tmp` is on the root filesystem and was nearly full, so
the clean PX4 patch round-trip used a temporary worktree under the repo and then
removed it.

## Gate A Failure

Command:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=wave2_gate_a_anchor ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python scripts/route_a_anchor_regression.py --run-id wave2_gate_a_anchor_20260703 --sim-speed-factor 1.25"'
```

Result:

- `ROUTE_A_REGRESSION_DECISION=REGRESSION_FAILED`
- `ROUTE_A_STRICT_COUNT=2`
- Summary:
  `runs/route_a_anchor_regression/wave2_gate_a_anchor_20260703/summary.md`
- Decontaminated results:
  `runs/route_a_anchor_regression/wave2_gate_a_anchor_20260703/decontam_results.json`

Anchor table:

| anchor | case | classical | mc_nn | strict S0 vs S3 | decision |
|---|---|---|---|---|---|
| pair1 | `rp48_62_rate2p45_2p90_w6_r6_f045` | S0 | S3 | true | STRICT_DIFFERENTIAL |
| pair2 | `rp48_62_rate2p45_2p90_w6_r6_f045_confirm1` | S0 | S3 | true | STRICT_DIFFERENTIAL |
| pair4 | `rp36_44_rate1p55_2p15_w3_r4_f038` | S0 | S1 | false | NO_STRICT_DIFFERENTIAL |
| pair5 | `rp32_40_rate1p30_1p95_w0_r4_f038` | S0 | S0 | false | NO_STRICT_DIFFERENTIAL |

The failed anchors were not invalid runs. All four matched pairs were valid;
pair4 and pair5 simply no longer reproduced strict `classical S0` vs `mc_nn S3`
under this Gate A rerun. Pair4 also failed the catastrophic P1/P2 sign gate, and
pair5 failed it as well.

## Gate Decision

Gate A requirement was: new shim patch round-trip applies, PX4 compiles, and
route-A anchors pair1/2/4/5 remain intact.

The patch and build portions passed, but the anchor regression failed. Per the
task guardrail, execution stopped here:

- no genome state-contam plumbing,
- no contamination-space probe,
- no main wave-2 campaign,
- no code/report commit,
- no push.

## Current Human Decision Point

The next decision is whether to investigate or relax the route-A anchor gate
before resuming wave-2. Concrete options include:

- rerun or extend route-A anchor diagnostics to determine whether pair4/pair5
  are stochastic boundary points under the rebuilt shim,
- keep pair1/pair2 as the active regression gate and demote pair4/pair5,
- inspect whether the added position channel changed timing/build artifacts in a
  way that should not affect the switch anchors,
- require a different anchor set before proceeding to Phase B.

No decision was made by the agent.
