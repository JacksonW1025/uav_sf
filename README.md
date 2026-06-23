# uav_sf Phase 1 Environment

This repository captures the Phase 1 environment for PX4 SITL with RAPTOR on Jetson AGX Orin arm64. The reproducible build runs in an `ubuntu:24.04` container and keeps PX4 source outside the image under `external/PX4-Autopilot`.

Phase 1 scope is environment only: build and headless smoke-test PX4 SITL with `mc_raptor`, stage the RAPTOR policy blob for module loading, and verify the ROS 2 / uXRCE-DDS topic path. No arming, takeoff, mode-switch flight, ULOG parsing, failure injection, or search is performed here.

## Status

- P0 complete: Docker is usable, the `uav_sf:phase1` image builds, PX4 `main` with RAPTOR builds, `make px4_sitl_raptor gz_x500` starts headless, and `mc_raptor` parameters plus external mode registration are present.
- P1 complete: ROS 2 Jazzy, `px4_msgs`, and Micro-XRCE-DDS-Agent are built; `ros2 topic list` sees `/fmu/out/*`.
- P1 deferred: combined RAPTOR + SIH board config (`px4_sitl_raptor_sih`) was not implemented in this pass.
- P2 partial: Gazebo Harmonic is installed and used headless; graphical display passthrough and extra later-phase Python tools beyond PX4 essentials were not validated.

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

## Evidence

Verification artifacts are kept under `docs/`:

- `docs/host_inventory.log`: host OS, L4T, Docker, ROS, Gazebo, and existing host PX4 inventory.
- `docs/px4_clone.log`: PX4 clone/submodule check, RAPTOR module presence, and `policy.tar` validation.
- `docs/px4_raptor_build.log`: RAPTOR SITL build and `gz_x500` target check.
- `docs/phase1_smoke.log`: headless PX4 startup, `mc_raptor` policy load, RAPTOR external mode registration, parameter check, `uxrce_dds_client status`, and clean shutdown observation.
- `docs/ros2_ws_build.log`: `px4_msgs` colcon build.
- `docs/microxrce_agent_build.log`: Micro-XRCE-DDS-Agent source build.
- `docs/phase1_dds_topics.log`: Agent/PX4 bridge smoke test and `/fmu/out/*` topic list.

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

## Next Step

M0 starts after this phase: classic-to-RAPTOR switching flight, missing-setpoint-to-NaN oracle sanity check, and ULOG recording. Those are intentionally out of scope for this repository state.

