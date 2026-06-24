# uav_sf Phase 1 Environment

This repository captures the Phase 1 environment for PX4 SITL with RAPTOR on Jetson AGX Orin arm64. The reproducible build runs in an `ubuntu:24.04` container and keeps PX4 source outside the image under `external/PX4-Autopilot`.

Phase 1 starts with the reproducible environment: build and headless smoke-test PX4 SITL with `mc_raptor`, stage the RAPTOR policy blob for module loading, and verify the ROS 2 / uXRCE-DDS topic path.

M0 is now also captured in this repository: a real SIH SITL run with classical takeoff to Hold, in-flight switch to RAPTOR external mode, ULOG capture, and the missing-setpoint oracle sanity check. M1 work adds the oracle MVP: fixed parameterized offboard tasks, ULOG metrics, and classical-vs-RAPTOR four-quadrant classification. M2 adds the first guided MAP-Elites search wrapper around the M1 runner. M2.5 adds shared EKF/GNSS estimator-pollution knobs and fixes the 4x early-shutdown failure, but the targeted delay scan did not produce a confirmed primary bug.

## Status

- P0 complete: Docker is usable, the `uav_sf:phase1` image builds, PX4 `main` with RAPTOR builds, `make px4_sitl_raptor gz_x500` starts headless, and `mc_raptor` parameters plus external mode registration are present.
- P1 complete: ROS 2 Jazzy, `px4_msgs`, and Micro-XRCE-DDS-Agent are built; `ros2 topic list` sees `/fmu/out/*`.
- M0 complete: `px4_sitl_raptor_sih` builds and SIH direct-launch runs the full classical takeoff to RAPTOR switch experiment with ULOG capture.
- M1 complete as an oracle MVP pipeline: tracked SIH-X500 airframe, parameterized fixed-theta offboard task, ULOG metrics, and classical-vs-RAPTOR four-quadrant runner. The manually tried anchors did not produce a primary-bug quadrant; see `docs/M1.md`.
- M2 complete as a guided-search first pass: fixed safety envelope, classical baseline decontamination, theta controllability matrix, MAP-Elites searcher, archive output, and confirmation protocol. The first search found one raw primary candidate, but it did not pass confirmation; confirmed primary batch is empty. See `docs/M2.md`.
- M2.5 complete as a blocker-unlock pass: shared EKF/GNSS estimator-pollution θ dimensions are implemented with ULOG fairness evidence, and `PX4_SIM_SPEED_FACTOR=4` now reaches `mission_end`. The 1x delay gradient and one harsh estimator-pollution probe were both-safe, so no confirmed primary bug was produced. Strict 1x-vs-4x metric invariance did not pass the existing M2 noise floor; see `docs/M2_5.md`.
- P2 partial: Gazebo Harmonic is installed and used headless; graphical display passthrough and extra later-phase Python tools beyond PX4 essentials were not validated.

## M0 Status

- Simulator: SIH (`px4_sitl_raptor_sih`, `sihsim_quadx`), not Gazebo fallback.
- Board overlay: `boards/px4/sitl/raptor_sih.px4board`, installed into the ignored PX4 tree by `scripts/install_raptor_sih_board.sh`.
- Launch note: the generated `make px4_sitl_raptor_sih sihsim_quadx` run target has a working-directory issue for `etc/init.d-posix/rcS`; M0 uses direct launch from `build/px4_sitl_raptor_sih` via `./bin/px4 .`.
- Mode switch: MAVLink `MAV_CMD_DO_SET_MODE` with PX4 custom main mode `AUTO` and external submode `EXTERNAL1`, confirmed by heartbeat `main=4 sub=11` and ULOG `nav_state=23`.
- ULOG: `docs/m0_run.ulg`; topic sanity is in `docs/m0_ulog_sanity.log`.
- NaN sanity: missing/stale setpoint did not produce active motor NaNs or disarm. Total `actuator_motors` NaNs were only unused quadrotor channels `control[4]` through `control[11]`; active channels `control[0]` through `control[3]` had zero NaNs.
- M0 scope stop: no M1 offboard task node, MAVSDK failure injection, metrics pipeline, divergence classifier, or search was added.

## Pinned Versions

- Host: Jetson AGX Orin, aarch64, Ubuntu 22.04.5, L4T R36.4.7.
- Docker Engine: 29.3.0, `DockerRootDir=/mnt/nvme/docker`, storage driver `overlayfs`.
- Container base: `ubuntu:24.04` semantics. `docker/build.sh` defaults to `public.ecr.aws/docker/library/ubuntu:24.04` because Docker Hub was unreliable from this host.
- Container OS: Ubuntu 24.04.4 LTS, aarch64.
- ROS 2: Jazzy.
- Gazebo: Harmonic / Gazebo Sim 8.14.0.
- PX4-Autopilot `main`: `3042f906abaab7ab59ae838ad5a530a9ef3df9a6`.
- `px4_msgs` `main`: `f7d9fcb65e2cdf4cf556f658bde55682403dcc8c`.
- Micro-XRCE-DDS-Agent `v2.4.3`: `73622810d984349b80bbac0ef55fc0b694d62222`.

## Reproduce

If the current shell has not picked up Docker group membership yet, wrap commands with `sg docker -c 'cd /mnt/nvme/uav_sf && ...'`. After logging out and back in, the plain commands below should work.

```bash
cd /mnt/nvme/uav_sf

./docker/build.sh
./scripts/clone_px4.sh

./docker/run.sh bash -lc "cd /workspace && ./scripts/build_px4_raptor.sh"
./docker/run.sh bash -lc "cd /workspace && ./scripts/smoke_px4_raptor.sh"

./docker/run.sh bash -lc "cd /workspace && ./scripts/setup_ros2_ws.sh"
./docker/run.sh bash -lc "cd /workspace && ./scripts/build_microxrce_agent.sh"
./docker/run.sh bash -lc "cd /workspace && ./scripts/smoke_dds_topics.sh"
```

Use a unique container name when running multiple commands concurrently:

```bash
CONTAINER_NAME=uav_sf_build ./docker/run.sh bash
```

To force Docker Hub instead of the ECR mirror:

```bash
BASE_IMAGE=ubuntu:24.04 ./docker/build.sh
```

## Reproduce M0

```bash
cd /mnt/nvme/uav_sf

sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m0_build ./docker/run.sh bash -lc "cd /workspace && ./scripts/build_px4_raptor_sih.sh"'

sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m0_run ./docker/run.sh bash -lc "cd /workspace && python3 -m pip install --break-system-packages pymavlink pyulog numpy -q && ./scripts/m0_run_experiment.sh"'
```

The M0 run writes:

```text
docs/m0_classical_takeoff.log
docs/m0_switch_to_raptor.log
docs/m0_run.ulg
docs/m0_ulog_info.log
docs/m0_ulog_sanity.log
docs/m0_oracle_sanity.md
```

## Reproduce M1

Build the RAPTOR SIH target with the tracked SIH-X500 v2 airframe:

```bash
cd /mnt/nvme/uav_sf

sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m1_build ./docker/run.sh bash -lc "cd /workspace && ./scripts/build_px4_raptor_sih.sh"'
```

Run one fixed theta through classical and RAPTOR and emit the four-quadrant result:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m1_sine ./docker/run.sh bash -lc "cd /workspace && python3 -m pip install --break-system-packages pymavlink pyulog numpy -q && source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && ./scripts/m1_diff_runner.py --theta config/m1_anchor_sine_5hz.json --skip-build"'
```

The runner writes:

```text
docs/m1_<tag>_classical.ulg
docs/m1_<tag>_raptor.ulg
docs/m1_<tag>_<controller>_metrics.json
docs/m1_diff_<tag>.json
docs/m1_diff_<tag>_summary.md
```

## Reproduce M2

Run the guided MAP-Elites first pass around the M1 evaluator:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m2_search ./docker/run.sh bash -lc "cd /workspace && python3 -m pip install --break-system-packages pymavlink pyulog numpy -q && source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && ./scripts/m2_map_elites.py --budget 8 --bootstrap 8 --seed 20260624 --run-id m2_map_elites_20260624 --run-timeout 150 --eval-timeout 420 --sim-speed-factor 1 --confirm-repeats 3 --max-confirm-candidates 3"'
```

The main M2 run writes:

```text
docs/m2_map_elites_20260624/archive.json
docs/m2_map_elites_20260624/evals.jsonl
docs/m2_map_elites_20260624/primary_candidates.json
docs/m2_map_elites_20260624/confirmations.jsonl
docs/m2_map_elites_20260624/summary.md
```

## Reproduce M2.5

Run the targeted 1x EKF/GPS delay gradient:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m25_scan ./docker/run.sh bash -lc "cd /workspace && python3 -m pip install --break-system-packages pymavlink pyulog numpy -q && source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && ./scripts/m2_5_estimator_scan.py --run --run-id m2_5_estimator_delay_scan_1x_20260624 --delays-ms 0 60 180 240 300 --sim-speed-factor 1 --run-timeout 180 --eval-timeout 480 --confirm-repeats 0"'
```

Run the speed-factor hover smoke:

```bash
sg docker -c 'cd /mnt/nvme/uav_sf && CONTAINER_NAME=uav_sf_m25_hover4x ./docker/run.sh bash -lc "cd /workspace && python3 -m pip install --break-system-packages pymavlink pyulog numpy -q && source /opt/ros/jazzy/setup.bash && source ros2_ws/install/setup.bash && PX4_SIM_SPEED_FACTOR=4 ./scripts/m1_diff_runner.py --theta config/m2_5_speed_hover.json --skip-build --run-timeout 150 --docs-dir docs/m2_5_speed_hover_4x_20260624 --safety-config config/m2_safety_envelope.json"'
```

## Evidence

Verification artifacts are kept under `docs/`:

- `docs/host_inventory.log`: host OS, L4T, Docker, ROS, Gazebo, and existing host PX4 inventory.
- `docs/px4_clone.log`: PX4 clone/submodule check, RAPTOR module presence, and `policy.tar` validation.
- `docs/px4_raptor_build.log`: RAPTOR SITL build and `gz_x500` target check.
- `docs/phase1_smoke.log`: headless PX4 startup, `mc_raptor` policy load, RAPTOR external mode registration, parameter check, `uxrce_dds_client status`, and clean shutdown observation.
- `docs/ros2_ws_build.log`: `px4_msgs` colcon build.
- `docs/microxrce_agent_build.log`: Micro-XRCE-DDS-Agent source build.
- `docs/phase1_dds_topics.log`: Agent/PX4 bridge smoke test and `/fmu/out/*` topic list.
- `docs/M0.md`: M0 run summary, reproduction commands, conclusions, and known issues.
- `docs/m0_raptor_sih_build.log`: combined RAPTOR + SIH board build.
- `docs/m0_raptor_sih_smoke.log`: SIH direct-launch startup, RAPTOR load/registration, and DDS topic evidence.
- `docs/m0_classical_takeoff.log`: classical takeoff to Hold evidence.
- `docs/m0_switch_to_raptor.log`: MAVLink `DO_SET_MODE` switch evidence and RAPTOR post-switch status.
- `docs/m0_run.ulg`: full M0 ULOG.
- `docs/m0_ulog_info.log`: `ulog_info` plus `ulog_messages` excerpt.
- `docs/m0_ulog_sanity.log`: required topic, mode switch, active motor NaN, and disarm sanity.
- `docs/m0_oracle_sanity.md`: missing-setpoint oracle conclusion.
- `docs/M1.md`: M1 oracle MVP summary, reproduction commands, fixed-theta results, determinism check, failure-injection status, and stop point.
- `docs/M2.md`: M2 guided search design, safety envelope, controllability matrix, MAP-Elites run results, unconfirmed primary candidate, and stop point.
- `docs/M2_5.md`: M2.5 shared-estimator-pollution implementation, fairness evidence, targeted delay scan, speed-factor smoke results, and stop point.
- `docs/m1_diff_anchor_sine_5hz.json`: representative both-safe fixed-theta diff result.
- `docs/m1_diff_anchor_heavy_338_step.json`: near-boundary heavy-mass diff result.
- `docs/m1_diff_anchor_heavy_max_step.json`: too-hard diff result.
- `docs/m1_diff_anchor_intref_lissajous.json`: manual RAPTOR internal-reference backup-anchor result.
- `docs/m1_determinism_anchor_sine_5hz_classical.log`: same-theta/same-controller repeat check.

Important observed lines:

```text
INFO  [mc_raptor] Policy loaded from file ./raptor/policy.tar
INFO  [mc_raptor] Raptor mode registration successful, arming_check_id: 0, mode_id: 23
INFO  [commander] External Mode 1: nav_state: 23, name: RAPTOR
DDS_TOPICS_FOUND=1
```

## Known Issues

- Docker Hub access was unreliable on this host, so `docker/build.sh` uses the public ECR Ubuntu mirror by default while preserving `ubuntu:24.04` base-image semantics.
- Docker group membership may require a new login session. Until then, run commands via `sg docker -c 'cd /mnt/nvme/uav_sf && <command>'`.
- PX4 CMake can cache an incomplete simulator configuration if `Tools/simulation/gz` was missing during first configure. `scripts/build_px4_raptor.sh` checks for `gz_x500` and forces reconfigure when needed.
- RAPTOR needs `policy.tar` in the simulated SD card path to load. The smoke scripts copy `src/modules/mc_raptor/blob/policy.tar` to `build/px4_sitl_raptor/rootfs/raptor/policy.tar`; this is a local SITL staging step, not a flight/upload procedure.
- Micro-XRCE-DDS-Agent `v2.4.3` does not provide a useful `--version` path in this setup, so the repository tag/commit and `MicroXRCEAgent -h` output are recorded instead.
- `MicroXRCEAgent` is built under `external/Micro-XRCE-DDS-Agent/build`; `scripts/smoke_dds_topics.sh` uses that persistent binary and sets `LD_LIBRARY_PATH` for the built libraries.
- M0 SIH direct launch requires passing rootfs `.` to PX4: `PX4_SIMULATOR=sihsim PX4_SIM_MODEL=sihsim_quadx ./bin/px4 .`.
- The inherited RAPTOR SITL config logs a non-blocking `vision_target_estimator` / `landing_target_estimator` conflict; the same warning was already visible in Phase 1 smoke output.
- M1 ROS output topics are versioned in this PX4/px4_msgs combination; `scripts/m1_offboard_task.py` expects `/fmu/out/vehicle_status_v4` and `/fmu/out/vehicle_local_position_v1`.
- The first finite bad-setpoint anchors did not produce a primary-bug quadrant because RAPTOR clips position/velocity error before policy inference; this is documented in `docs/M1.md`.
- M2.5 fixes the original 4x early-shutdown failure: 4x runs now reach `mission_end`. However, 1x-vs-4x metric invariance did not pass the existing M2 noise floor, so use 4x for smoke/triage only and keep primary-bug confirmation at 1x until this is root-caused.

## Next Step

M2b can start after this state as a full guided rerun that includes `A_estimator`, but primary confirmation should stay at 1x unless speed-factor invariance is resolved. M3 remains out of scope: random/grid baseline comparison, no-feedback ablation, systematic failure taxonomy, and large repeat campaigns are still not part of this commit.
