# AGX Thor environment and migration report

## Host and formal-container inventory

| Component | AGX Thor host | Formal experiment boundary |
| --- | --- | --- |
| device / architecture | NVIDIA Jetson AGX Thor Developer Kit / aarch64 | ARM64 |
| L4T | R38.2.1 | host kernel boundary only |
| JetPack | `nvidia-jetpack` meta-package not installed | not required |
| operating system | Ubuntu 24.04.3 LTS | Ubuntu 24.04.4 LTS / Noble |
| kernel | 6.8.12-tegra | inherited from host |
| NVIDIA driver | 580.00 | not exposed to the study |
| CUDA | toolkit/runtime 13.0 on host | not exposed and not required |
| Python | host shell may select Conda 3.13.5 | locked Python 3.12.3 |
| ROS / RMW | host ROS 2 Jazzy may be sourced | Jazzy / `rmw_fastrtps_cpp` |
| Gazebo | host Harmonic paths have multiple providers | container Gazebo Sim 8.11.0 |
| Docker | 27.5.1; default runtime `nvidia` | explicit `runc`, network none, no GPU |
| NVIDIA container toolkit | 1.18.0-rc.1 | not used by the study runtime |

L4T R38.2.1 belongs to the JetPack 7 generation, but the absence of the
`nvidia-jetpack` meta-package means this machine is not reported as a complete,
versioned JetPack installation.

## Baseline-to-runtime differences

| Area | Clean baseline | Thor result |
| --- | --- | --- |
| source identities | four exact candidate commits and patch hashes | same candidates independently built and attested |
| build path | source preparation only; no complete PX4/ROS/Agent recipe | recursive sources, PX4 SITL, ROS workspace, Agent, and project packages built in the image |
| Python | undeclared native interpreter; host resolves to Conda 3.13 | Python 3.12 virtual environment inside the image |
| ROS / Gazebo | reference Noble/Jazzy image only; host paths could leak | complete Noble/Jazzy/Harmonic runtime with host paths rejected by preflight |
| observation | normalized JSON input existed, but no runtime producer | live ROS/lifecycle sidecars plus uORB-to-ULog RouteObservability and clock bridge |
| execution | no PX4/Gazebo launcher or legal transition fixtures | isolated headless `gz_x500` runner for Offboard, Dynamic Mode, and Mode Executor |
| evidence | no formal environment, attempt, or retained result | fail-closed Gate, Oracles, raw manifests, compact results, and hash-chained ledgers |
| parallelism | not defined | qualified concurrency four with isolated CPU, ROS, PX4, Gazebo, XRCE, ports, files, and process groups |
| GPU libraries | no project dependency | none added |

The exact upstream source commits remain:

- PX4-Autopilot `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`;
- `px4_msgs` `18ecff03041c6f8d8a0012fbc63af0b23dd60af1`;
- `px4_ros2_interface_lib` `c3e410f035806e8c56246708432ded09c976434b`;
- Micro-XRCE-DDS-Agent `73622810d984349b80bbac0ef55fc0b694d62222`.

The PX4 SITL binary digest is
`sha256:168c9a3d2e05d07a54d01f420d7a47dc58977eec0ece544c8c454e4f0c6bf619`.

## Changes and installation scope

No host apt package, Conda package, CUDA component, TensorRT component, PyTorch
package, BSP, driver, kernel, or firmware was installed or replaced. All new
software builds and package locks live in Docker images or the repository.

Repository additions include the complete ARM64 runtime image, exact direct and
resolved package manifests, source/build verification, ROS runtime packages,
public transition fixtures, ULog extraction and integrity checks, clock-domain
closure, Evidence Gate integration, safety/cleanup supervision, isolation,
formal accounting, campaign scheduling, concurrency qualification, and the two
Thor evidence studies. Raw evidence remains in ignored `runs/`; only digests and
compact results are tracked.

## Formal study closure

The primary study registered and closed 180 launches: 131 accepted, 20
observability rejected, 28 timeout, and one environment failure. Nineteen of 21
primary cells reached target; the two invalid-plan cells reached cap and remain
reported as `MEASUREMENT_INSUFFICIENT`.

The separately preregistered supplemental study registered and closed 20 new
launches, all accepted. Both corrected cells reached 10/10 accepted evidence
sets. Across both studies there are 200 closed formal launches and 151 accepted
evidence sets. Accepted traces contain 94 overall Oracle passes and 57 overall
Oracle violations. All 200 retained ULogs passed the registered integrity and
RouteObservability gap checks.

No earlier-device result is imported, compared, or counted.

## Readiness and remaining risks

The locked container, build path, runtime entry, evidence pipeline, formal
accounting, and stable parallel execution are ready for a new experiment matrix.
Any later state-aware study still needs its own preregistered cells, seeds,
targets, caps, and hypotheses; the environment is ready, but no later empirical
claim is implied by this readiness.

Known bounded risks are the observed route/freshness/successor violations, the
20 primary observability rejections, the one diagnosed live-JSONL race in the
primary environment, and the fact that claims cover only ARM64 Thor PX4 SITL,
`gz_x500`, and headless Gazebo Harmonic. Hardware-in-the-loop and real flight
remain outside scope.
