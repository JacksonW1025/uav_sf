# raptor_unclipped Ablation Preflight - 20260707

## Scope

Preparation only. The formal 24-eval unclipped RAPTOR ablation was not started.

This experiment treats `raptor_unclipped` as a new SUT. It is only for locating the source of RAPTOR robustness (input clipping versus internal/controller effects), not for reopening learned-specificity claims.

## Implementation

- Patch: `patches/px4/raptor_unclipped.patch`
- Source touched by the patch: `external/PX4-Autopilot/src/modules/mc_raptor/mc_raptor.cpp`
- Original clipping constants: `max_position_error = 0.5`, `max_velocity_error = 1.0` in `mc_raptor.hpp`.
- Patched semantics: `observe()` now assigns target-frame position and linear velocity errors directly to `observation.position[]` and `observation.linear_velocity[]`.
- Applied source lines after patch:
  - position assignment: `mc_raptor.cpp:388-390`
  - velocity assignment: `mc_raptor.cpp:399-401`

The patch was checked forward and reverse, then reapplied so the local PX4 source tree remains in the unclipped state.

## Board And SUT

- Board file: `boards/px4/sitl/raptor_unclipped_sih.px4board`
- Installer: `scripts/install_raptor_unclipped_sih_board.sh`
- Build script: `scripts/build_px4_raptor_unclipped_sih.sh`
- Build target: `px4_sitl_raptor_unclipped_sih`
- Build log: `docs/m0_raptor_unclipped_sih_build.log`
- Build evidence: final log ends with `Linking CXX executable bin/px4` and `sihsim_quadx: phony`.

`scripts/m2_map_elites.py` now registers `raptor_unclipped` with:

- `controller="raptor"`
- `identity_key="raptor_identity"`
- `input_clipping=False`
- distinct runner build dir: `external/PX4-Autopilot/build/px4_sitl_raptor_unclipped_sih`

`scripts/m1_diff_runner.py` now honors `PX4_RAPTOR_BUILD_DIR`, so `raptor_unclipped` uses the distinct unclipped board instead of the clipped `px4_sitl_raptor_sih` build.

## Driver

- Driver: `scripts/run_raptor_unclipped_ablation.py`
- Default SUT: `raptor_unclipped`
- Default sim speed: `1.25`
- Plan source:
  - anchors from `runs/campaigns/raptor_gate0_anchor_recheck_20260705/anchor_plan.json`
  - attitude-band BASE from `runs/campaigns/raptor_switch_severity_dense_sweep_20260705/sweep_config.json`
- `--list-only` prints 24 planned evals: 8 theta points x 3 seeds.
- Theta IDs: `pair1`, `pair2`, `pair4`, `pair5`, `attitude_deg_40`, `attitude_deg_42`, `attitude_deg_45`, `attitude_deg_48`.

Current local cache note: pair5 has mixed classical cache in the clipped anchor artifact, so the driver will rerun paired classical for pair5 unless a stable matching cache is added. Other listed points use cached classical severity where stable.

## Smoke

Smoke command used a single high-error anchor eval only:

`python scripts/run_raptor_unclipped_ablation.py --run-id raptor_unclipped_ablation_smoke2_20260707 --no-resume --max-evals 1 --run-timeout 230`

Smoke result:

- theta: `pair1`
- seed: `2026062940`
- theta axes: wind `6 m/s`, requested rate `2.45-2.90 rad/s`, attitude band `48-62 deg`
- total evals run in final smoke: `1`
- valid evals: `1`
- classical severity: `S0` from cache
- clipped RAPTOR severity: `S0` from clipped campaign cache
- `raptor_unclipped` severity: `S0`
- unresolved failsafe: none reported by validity/decontamination gate

RAPTOR identity gate:

- passed: `true`
- `raptor_status_present=true`
- `raptor_input_present=true`
- `raptor_status_active_samples=7755`
- `raptor_input_samples=10680`
- `raptor_input_active_samples=7758`
- target nav state: `23`
- `neural_control_present=false`
- `policy_tar_staged=true`

Note: an earlier smoke attempt failed before flight because the local `ros2_ws/install` overlay had stale Humble/Python 3.10 `px4_msgs` artifacts while the container is Jazzy/Python 3.12. I rebuilt the ignored `ros2_ws` overlay package `px4_msgs` under Jazzy and reran the same one-eval smoke successfully.

## Unclipping Evidence

Dump tool output:

- `runs/campaigns/raptor_unclipped_ablation_smoke2_20260707/raptor_input_dump.json`

Full active-topic scan:

- `runs/campaigns/raptor_unclipped_ablation_smoke2_20260707/raptor_input_max_abs.json`

Observed active `raptor_input` maxima:

- max abs position error: `14.005464553833008 m` (`position[0]`)
- old position clip bound: `0.5 m`
- max abs linear velocity error: `6.921072483062744 m/s` (`linear_velocity[0]`)
- old velocity clip bound: `1.0 m/s`

Conclusion: the unclipped ablation is active. Large position and velocity errors reached the policy input and exceeded the old clipped RAPTOR bounds.

## Verification

Passed:

- `python -m py_compile scripts/run_raptor_unclipped_ablation.py scripts/m2_map_elites.py scripts/m1_diff_runner.py`
- `bash -n scripts/install_raptor_unclipped_sih_board.sh scripts/build_px4_raptor_unclipped_sih.sh`
- `python -m unittest tests.test_campaign_runner tests.test_validity_automation`
- `python scripts/run_raptor_unclipped_ablation.py --run-id raptor_unclipped_ablation_20260707 --list-only`
- `git -C external/PX4-Autopilot apply --check patches/px4/raptor_unclipped.patch` after reversing to the clipped source
- `git -C external/PX4-Autopilot apply --reverse --check patches/px4/raptor_unclipped.patch` after reapplying

Ignored/generated artifacts were kept out of git status: `external/`, `runs/`, `*.ulg`, build logs, and `ros2_ws/`.

## GO Command

Run this only when explicitly starting the formal 24-eval comparison:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=raptor_unclipped_ablation_20260707 ./docker/run.sh bash -lc "source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && python scripts/run_raptor_unclipped_ablation.py --run-id raptor_unclipped_ablation_20260707 --sim-speed-factor 1.25"'
```

Expected wall time: about 1.1 h if classical is fully reused; up to about 2.2 h if theta points require paired classical reruns. With the current local cache, pair5 is expected to trigger paired reruns unless a stable pair5 classical cache is supplied.

## Stop State

Stopped at preparation-complete state and waiting for an explicit GO instruction. The formal 24-eval ablation has not been launched.
