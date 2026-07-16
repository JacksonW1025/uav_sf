# Wave-2 Preflight Report - 2026-07-03

Scope: preflight only. No shim repair, no genome changes, no Step C implementation, and no SITL evals were run.

## Git Sync

Initial state after `git fetch --prune origin`:

- Branch: `main`
- Upstream: `origin/main`
- Remote: `git@github.com:JacksonW1025/uav_sf.git`
- Local ahead before artifact commit: `db9adc7 Add multi-policy differential spectrum`
- Public before push: `origin/main` at `118d58f Run switch severity campaign`

Phase 1 pushed range:

- `db9adc7 Add multi-policy differential spectrum`
- `03f5155 Add campaign artifact docs`

Push result: `118d58f..03f5155 main -> main`. Public `origin/main` was synced through `03f5155` before this report commit.

Push safety checks before the Phase 1 push:

- `python -m py_compile scripts/*.py`: pass
- `python -m unittest discover -s tests`: pass, 31 tests OK
- `bash -n scripts/*.sh docker/*.sh`: pass
- changed JSON `jq empty`: pass
- `git diff --check`: pass
- `git diff --cached --check`: pass
- `git ls-files` / staged scan: no `*.ulg`, no checkpoint, no `runs/`, no `docs/**/evals/`, no large binary; largest tracked file after staging was still a JSON artifact under 330 KB, largest newly staged file about 47 KB.

## Untracked Item Classification

All visible untracked items were small `docs/` or `config/` artifacts. Ignored local outputs stayed ignored (`*.ulg`, `*.log`, `docs/**/evals/`, `runs/`, `__pycache__`).

| Path | Classification | Action | Rationale |
|---|---|---:|---|
| `config/m2_primary_bugs/*.json` | Reproducible theta artifact | tracked in `03f5155` | 20 switch severity primary-bug theta configs; JSON only; no ulog/checkpoint; each records `uses_state_shim: false` and `state_contam_status: DEFERRED`. |
| `docs/PROJECT_NARRATIVE_CONTEXT_v8 (1).md` | Consolidated narrative/reproduction context | retained predecessor | Durable project state context referenced by this task and future agents. |
| `docs/fullscale_fuzzing_preflight_checklist_v0_1 (1).md`, `docs/oracle_map_and_property_set_v0.1.md` | Design/report artifact | tracked in `03f5155` | Small markdown design/preflight docs. |
| `docs/smoke_2p3_*_20260626/` | Report + theta artifact | tracked in `03f5155` | Summaries, metadata, archive/progress/evals JSONL, theta JSON; ignored `docs/**/evals/` payloads and logs were not added. |
| `docs/validity_automation_*_20260627/` | Report + theta/confirmation artifact | tracked in `03f5155` | Small summary/metadata/progress/candidate/confirmation artifacts; no ulogs or run-root payloads. |

Ambiguous items: none after inspection. The only potentially ambiguous group was the generated `docs/smoke_*` / `docs/validity_*` run-summary directories; because the repository already tracks comparable `docs/.../results.json`, metrics, theta, and summary artifacts, and because bulky eval/log/ulog payloads are ignored, these were classified as reproducible report artifacts rather than local run directories.

## Blocker Scope

### 1. Shim Patch Drift

Patch: `patches/px4/m2b_state_shim.patch`

PX4 state inspected:

- PX4 worktree: `external/PX4-Autopilot`
- PX4 HEAD: `3042f906ab`
- The six patch target files are already modified in the PX4 worktree.
- Current local diff across those six files: `559 insertions, 2 deletions`.

Dry-run results:

- Running `git apply --check` from the repo root fails because the patch paths are PX4-relative (`src/...`).
- Running from `external/PX4-Autopilot`, forward apply fails.
- `git apply --3way --check` from PX4 fails for all six target files with `does not match index`, because the target files are already dirty.
- Reverse apply also fails in all six target files, so the current PX4 dirty shim is not exactly the reverse of the tracked patch.

Per-file drift map:

| File | Current PX4 diff | Forward check result | Reverse check result | Scope |
|---|---:|---|---|---|
| `src/modules/ekf2/EKF2.cpp` | `+182/-0` | 3 hunks would apply only with large offsets (`+3454`, `+2320`, `+1689`) | fails near original shim block | Must inspect; likely stale context / duplicate-risk if applied blindly. |
| `src/modules/ekf2/EKF2.hpp` | `+33/-0` | 3 hunks would apply with offsets (`+609`, `+325`, `+249`) | fails near declaration hunk | Must inspect; shim declarations already present but context stale. |
| `src/modules/ekf2/EKF2Selector.cpp` | `+184/-0` | 3 hunks would apply with offsets (`+1007`, `+654`, `+528`) | fails near original shim block | Must inspect; same stale-context / duplicate-risk pattern. |
| `src/modules/ekf2/EKF2Selector.hpp` | `+34/-1` | first 2 hunks apply with offsets; final parameter-list hunk fails at old line 254 | fails near method declaration hunk | Hard forward failure; needs manual parameter-list merge. |
| `src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.cpp` | `+105/-0` | 2 hunks would apply with offsets (`+1009`, `+140`) | fails near original shim block | Must inspect; stale context / duplicate-risk pattern. |
| `src/modules/sensors/vehicle_angular_velocity/VehicleAngularVelocity.hpp` | `+21/-1` | first 2 hunks apply with offsets; final parameter-list hunk fails at old line 197 | fails near method declaration hunk | Hard forward failure; needs manual parameter-list merge. |

Cost estimate: mandatory for wave-2 state contamination. This is a six-file manual 3-way realignment / patch regeneration job, not a one-hunk fix. The shim code appears present in the PX4 dirty worktree, but the tracked patch is stale enough that a clean setup needs rebase/regeneration plus PX4 build and route-A/anchor regression before campaign use.

### 2. Genome State-Contamination Axis

`scripts/theta_genome.py` already has state-contamination names and bounds:

- `disturbance_type == "state_contam"` exists in `DISTURBANCE_TYPES`.
- Variables exist: `fake_velocity_bias_m_s`, `fake_angular_rate_bias_rad_s`, `position_estimate_jump_m`.
- `genome_severity()` includes a `state_contam` score.

But the axis is not routable today:

- All three state-contam `VariableSpec` entries have `enabled=False`.
- Their `route_status` is `DEFERRED - pending m2b_state_shim.patch drift`.
- Default generation uses `SHIM_FREE_DISTURBANCE_TYPES = ["wind", "physics_mismatch", "switching", "step"]`.
- `validate_genome()` rejects `disturbance_type == "state_contam"` unless `allow_deferred=True`.
- `theta_from_genome()` calls `assert_valid_genome(..., allow_deferred=False)`.
- Generated theta metadata still reports `state_contam_status: DEFERRED - pending m2b_state_shim.patch drift`.

Missing for wave-2: enable state-contam as a real subspace, plumb these genome variables into M2B shim PX4 params/profiles, define descriptor/campaign routing for the contamination axis, and add focused tests. The variable names are present, but wave-2 cannot generate executable state-contam theta until shim routing is repaired.

### 3. Step C / Timing

`scripts/m1_offboard_task.py` uses PX4 topic timestamps for event elapsed time (`update_time()` and `elapsed_s()`), but setpoint publication is still driven by a ROS wall-clock timer:

- Timer line: `self.timer = self.create_timer(1.0 / self.wall_timer_hz, self.tick)`
- `wall_timer_hz = rate_hz * PX4_SIM_SPEED_FACTOR`, capped by `max_wall_timer_hz`

Status: Step C is not done. The task still emits setpoints from a wall-clock `create_timer`, not a lockstep sim-time scheduler.

Impact: Step C is a throughput optimization, not a correctness prerequisite for wave-2. Wave-2 can run the same way as wave-1 and the switch campaign: serial `N=1` at the known stable speed. If Step C is implemented, it must be followed by route-A regression and anchor regression before using higher speed or parallel SITL.

## Wave-2 Readiness

Wave-2 is not campaign-ready yet.

Required before a real state-contamination wave-2 setup:

1. Rebase/regenerate `m2b_state_shim.patch` across all six PX4 files.
2. Enable and route the genome `state_contam` axis into executable shim parameters.

Optional before first wave-2 campaign:

3. Step C timing rewrite for throughput. This can be deferred if the first wave-2 run is serial `N=1`.

Human decision points left open:

- Whether to do shim realignment first, or Step C first.
- Whether to defer Step C and run initial wave-2 serial `N=1`.
