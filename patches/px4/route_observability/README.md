# PX4 route-observability patch

Base PX4 commit: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`

`route_observability_topics.patch` adds one structured uORB topic and three
publication points for the Family A multicopter path:

1. `mc_pos_control` records receipt of a new `trajectory_setpoint`;
2. `mc_rate_control` records the writer of the allocator torque input;
3. `control_allocator` records the writer of `actuator_motors`.

The logger records the topic at up to 100 Hz. The patch contains no branch that
changes a control decision, setpoint, controller state, scheduling interval, or
actuator value. It emits no high-rate console text. Sequence counters are local
to each instrumented publisher; ordering uses the PX4 boot-time timestamp.

The scope is intentionally narrow: it validates the locked multicopter
position/rate/control-allocation path used by P0. It does not claim writer
coverage for rover, spacecraft, direct-actuator, or Family B modules.

Use `scripts/setup/prepare_observability_px4.sh`. It leaves the canonical locked
checkout clean and creates an ignored detached worktree for the instrumented
build. Re-running the script detects an already applied patch.
