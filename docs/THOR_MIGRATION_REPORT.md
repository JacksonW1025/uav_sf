# AGX Thor environment and migration report

This file records environment and migration facts only. Research direction and
claim boundaries are defined in [NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md) and
[CURRENT_STATUS.md](CURRENT_STATUS.md).

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

The recorded Thor environment included an ARM64 runtime image, package
manifests, source/build verification, ROS runtime packages, public transition
fixtures, ULog extraction, clock closure, Gate/Oracle processing,
safety/cleanup, isolation, accounting, campaign scheduling, the two Stage A1
studies, the two Stage A2 studies, and the completed setpoint-stall timing
slice. Raw evidence remains in ignored `runs/`; only digests and compact results
are tracked.

Those high-level build and execution components belonged to their bound Git
revisions. The current V8 checkout intentionally removes the old patch bundle,
flight image, closure, evaluator, and runner. This report records environment
facts; it is not a current build instruction.

The campaign scheduler now separates each parallel batch into a live phase
and an offline evidence-processing phase. A barrier proves that every live
container has stopped before ULog parsing, clock fitting, Gate evaluation, and
Oracle execution begin. Four-way regression passed with 4/4 admissible traces.
A five-way trial also produced 5/5 admissible traces, but it was not promoted:
maximum clock uncertainty increased from 5.505 ms to 15.068 ms and one matched
Dynamic baseline changed its timing-sensitive Freshness interpretation. Formal
concurrency was therefore fixed at four for that runtime, and no additional
six-way trial was run. A future V8 runtime must qualify concurrency again.

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

Stage A2 then used a separately qualified position-only straight-line
workload. Its primary study closed 51 launches but remains
`MEASUREMENT_INSUFFICIENT` because a trace-closure defect prevented three cells
from reaching target. An independent remediation changed only that evidence
rule and the public takeoff-before-transition obligation, then used a new
image, environment, seeds, ledger, and denominator. It closed 26/26 launches
as accepted and admissible: 10 normal PASS and 16 deliberate freshness
VIOLATION. These Stage A2 counts remain separate from the Stage A1
`200 / 151 / 94 / 57` accounting.

The Section 7 vertical slice adds 18 separately preregistered formal launches.
All 18 are closed, accepted, admissible, physically valid, and overall
freshness `VIOLATION`. Its 54-event ledger and compact results remain separate
from both Stage A1 and Stage A2. Across all retained Thor formal studies there
are now 295 closed launches.

Earlier narrative work documented a separate prior Orin evidence lineage, but no
earlier-device evidence artifact is imported into, numerically compared inside,
or counted in the Thor formal corpus. Those source artifacts are retained on
neither the current working branch nor `origin/main`; exact reuse requires separately supplied
provenance and evidence.

## Current V8 boundary and remaining risks

The setpoint-stall timing slice closed 18/18 formal launches across a fixed
policy, bounded-random timing, and a prototype feedback policy. All were
accepted and admissible under the frozen study contract. The fixed policy
covered one bin; the other two covered three, but random and the prototype tied
and exposed only the same freshness signature. These facts support bounded
executability of that historical prototype, not V8 method readiness or a
general strategy ranking.

The current checkout has no active Thor flight image or runner. Before any new
formal campaign it must establish independent identity/effect observation,
combined physical/evidence admissibility, the complete semantic state, a
provenance-backed route/action corpus, four fair strategies, finding
confirmation, repeated-campaign statistics, and new resource-interference
qualification. Environment history cannot answer the method evaluation.

Known bounded risks are the observed route/freshness/successor violations, the
Stage A1 primary observability rejections, the diagnosed live-JSONL race, the
closed insufficient Stage A2 primary study, and the fact that claims cover only
ARM64 Thor PX4 SITL, `gz_x500`, and headless Gazebo Harmonic. Stage A2 adds one
bounded straight-line context; hardware-in-the-loop and real flight remain
outside the completed evidence.
