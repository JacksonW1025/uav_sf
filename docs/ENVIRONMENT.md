# Phase 1 Environment Notes

## Architecture

The Jetson host is used as a Docker host only. PX4, ROS 2 Jazzy, Gazebo Harmonic, `px4_msgs`, and Micro-XRCE-DDS-Agent are installed or built inside the `uav_sf:phase1` container based on Ubuntu 24.04.

PX4 source is bind-mounted from the host:

```text
/mnt/nvme/uav_sf/external/PX4-Autopilot -> /workspace/external/PX4-Autopilot
```

The image intentionally does not bake in the PX4 source tree, because PX4 `main` is large and changes frequently. Reproducibility is provided by the recorded commit SHA and scripts.

## Host Inventory

Captured in `docs/host_inventory.log` before environment changes:

- Kernel/arch: `5.15.148-tegra`, `aarch64`.
- OS: Ubuntu 22.04.5 LTS.
- L4T: R36, revision 4.7.
- Host ROS: Humble.
- Host Gazebo: Gazebo Sim 8.10.0.
- Existing host PX4: `/mnt/nvme/px4_work/PX4-Autopilot`, `v1.15.0`, no `src/modules/mc_raptor`.

Host changes made for this phase:

- Docker Engine 29.3.0 is installed and validated with `hello-world`.
- User `car` was added to the `docker` group; a new login session is needed for normal socket access.
- Docker data was moved to NVMe. Current state:

```text
DockerRootDir=/mnt/nvme/docker
Driver=overlayfs
ServerVersion=29.3.0
Architecture=aarch64
```

## Container Inventory

Verified in `uav_sf:phase1`:

```text
PRETTY_NAME="Ubuntu 24.04.4 LTS"
aarch64
ROS_DISTRO=jazzy
Gazebo Sim, version 8.14.0
cmake version 3.28.3
numpy 2.5.0
```

The Dockerfile installs PX4 build dependencies directly instead of running `Tools/setup/ubuntu.sh` by default. `scripts/build_px4_raptor.sh` still supports `SETUP_DEPS=1` to run:

```bash
bash Tools/setup/ubuntu.sh --no-nuttx
```

inside the container if future PX4 dependency drift requires it.

## Exact Source Pins

```text
PX4-Autopilot main: 3042f906abaab7ab59ae838ad5a530a9ef3df9a6
px4_msgs main: f7d9fcb65e2cdf4cf556f658bde55682403dcc8c
Micro-XRCE-DDS-Agent v2.4.3: 73622810d984349b80bbac0ef55fc0b694d62222
```

PX4 required submodules are initialized by `scripts/clone_px4.sh`. Full submodule checkout can be requested with:

```bash
PX4_SUBMODULE_MODE=full ./scripts/clone_px4.sh
```

The RAPTOR policy blob was confirmed as a real POSIX tar archive:

```text
src/modules/mc_raptor/blob/policy.tar
136192 bytes
```

## Build and Smoke Commands

Build image:

```bash
./docker/build.sh
```

Clone/pin PX4:

```bash
./scripts/clone_px4.sh
```

Build RAPTOR SITL:

```bash
./docker/run.sh bash -lc "cd /workspace && ./scripts/build_px4_raptor.sh"
```

Headless RAPTOR smoke:

```bash
./docker/run.sh bash -lc "cd /workspace && ./scripts/smoke_px4_raptor.sh"
```

ROS 2 / DDS setup and smoke:

```bash
./docker/run.sh bash -lc "cd /workspace && ./scripts/setup_ros2_ws.sh"
./docker/run.sh bash -lc "cd /workspace && ./scripts/build_microxrce_agent.sh"
./docker/run.sh bash -lc "cd /workspace && ./scripts/smoke_dds_topics.sh"
```

## Validation Summary

PX4 RAPTOR build:

```text
ninja: no work to do.
gz_x500: phony
```

RAPTOR module smoke:

```text
INFO  [mc_raptor] Policy checkpoint ./raptor/policy.tar exists
INFO  [mc_raptor] Policy loaded from file ./raptor/policy.tar
INFO  [mc_raptor] Raptor mode registration successful, arming_check_id: 0, mode_id: 23
INFO  [commander] External Mode 1: nav_state: 23, name: RAPTOR
x +   MC_RAPTOR_ENABLE [553,1027] : 1
x     MC_RAPTOR_INTREF [554,1028] : 0
x     MC_RAPTOR_OFFB [555,1029] : 0
PX4_SHUTDOWN_OBSERVED=1
```

DDS bridge smoke:

```text
INFO  [uxrce_dds_client] init UDP agent IP:127.0.0.1, port:8888
INFO  [uxrce_dds_client] successfully created rt/fmu/out/sensor_combined data writer
/fmu/out/sensor_combined
/fmu/out/vehicle_status_v4
DDS_TOPICS_FOUND=1
```

## Deferred Work

The combined RAPTOR + SIH board target remains deferred. The intended next step is to merge the relevant SIH module settings from `boards/px4/sitl/sih.px4board` with RAPTOR settings from `boards/px4/sitl/raptor.px4board`, then validate a target such as:

```bash
make px4_sitl_raptor_sih sihsim_quadx
```

No flight, arming, ULOG work, failure injection, or search work was performed in this phase.

