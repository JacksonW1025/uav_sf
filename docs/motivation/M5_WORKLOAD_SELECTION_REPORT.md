# M5 real workload selection report

## Selection

Primary workload: **Aerostack2** at `a8e7318b8d1d7c5adc580e8a16374357773bc11a`.

Backup workload: **MRS UAV System ROS2** at `99e59bf355bcb80bb69165e1d466f0d17f76bd17`.

Aerostack2 is selected because it is native ROS 2, BSD-licensed, actively maintained, modular, and exposes task phases, ROS action cancellation, Offboard/manual services, hover/land/emergency paths, and simulation assets in a compact source tree. Its behavior events and motion-reference topics can be acquired without modifying the autonomy logic. The PX4 platform mapping still has to be confirmed at runtime; source-level behavior changes are not automatically counted as route handoffs.

MRS is the backup because it has a dedicated PX4 API, ROS 2 Jazzy support, companion-computer deployment, safety/control/planning components, and documented simulator packages. Its code and rolling packages are distributed across `mrs_uav_system`, `mrs_uav_core`, `mrs_uav_px4_api`, and simulator repositories, so a complete exact-commit lock and adapter cost are higher.

KR Autonomous Flight is not selected for the first acquisition. It is a valuable real fast-flight stack with a MAVROS attitude bridge, planner aborts, LandTracker, and simulation material, but the main route is ROS 1, the ROS 2 port is explicitly incomplete, and its Penn license is research/non-commercial rather than a standard permissive OSS license.

## Interface audit

For Aerostack2, capture:

- Offboard/manual service requests and results;
- behavior goal, feedback, cancellation, and result status;
- go-to/follow-path/land motion references;
- alert events for hover, land, aircraft emergency land, and kill-switch (the kill-switch is excluded from flight execution);
- concrete PX4 nav state, setpoint consumption, allocator input, and writer evidence from this repository's collectors.

For MRS, acquisition requires a second audit that pins the PX4 API, core, and simulator dependency commits. Candidate events are PX4 API mode/arm/land requests, tracker/controller selection, safety-manager output, and companion/PX4 link health.

This phase performs selection and trace planning only. It does not install or execute either large stack. The full comparison is in [WORKLOAD_CANDIDATES.tsv](WORKLOAD_CANDIDATES.tsv).
