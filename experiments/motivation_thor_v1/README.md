# Thor Motivation Study

This directory is the compact, Git-tracked record for the new Family A study
on AGX Thor. The target is PX4 SITL with `gz_x500` in headless Gazebo Harmonic,
inside a complete ARM64 Ubuntu Noble and ROS 2 Jazzy container.

The host contributes only L4T, the kernel, Docker, CPU, memory, storage, and
container scheduling. The container supplies every experiment executable and
user-space dependency. CUDA, TensorRT, PyTorch, host Conda, host ROS workspaces,
and host Gazebo paths are outside the experiment dependency set.

Tracked here are the preregistration, exact matrix, environment attestation,
threshold rationale, append-only attempt ledger, compact closures, Gate and
Oracle results, raw-evidence digest manifests, compact summary, and final
report. Complete ULogs, JSONL streams, process logs, and build products stay
under ignored `runs/`.

No formal launch is permitted until the matrix revision, container image ID,
environment identity, thresholds, sample targets, caps, and concurrency are
all frozen and mutually verified.
