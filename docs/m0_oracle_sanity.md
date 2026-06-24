# M0 Oracle Sanity: Missing Setpoint to NaN

## Setup

- Simulator: `px4_sitl_raptor_sih` with `sihsim_quadx`.
- RAPTOR mode: external mode `mode_id 23`, selected via MAVLink `MAV_CMD_DO_SET_MODE`.
- Offboard replacement: `MC_RAPTOR_OFFB=0`.
- Internal reference: `MC_RAPTOR_INTREF=0`.
- No ROS 2 offboard task node or external setpoint stream was used.
- ULOG: `docs/m0_run.ulg`.

## Expected Behavior

Current RAPTOR has a stale/missing setpoint guard. The literal missing-setpoint sanity check is therefore expected to exercise the hold fallback, not to create NaN policy inputs.

If a learning controller emits NaN on an active motor command, PX4's direct actuator path maps that to disarmed output. The observable oracle signal is active `actuator_motors` NaN together with an unexpected disarm.

## Source-Level Chain

The naive missing-setpoint trigger is cut off before it can reach the policy as NaN:

1. `MC_RAPTOR_OFFB=0` keeps RAPTOR as a separate external mode instead of replacing Offboard. The module parameter text says this mode holds position without requiring external setpoints, and `mc_raptor.cpp` wires this through `enable_replace_internal_mode = _param_mc_raptor_offboard.get()`.
2. Incoming `trajectory_setpoint` updates pass a finiteness gate. RAPTOR only accepts a setpoint when position, yaw, velocity, and yawspeed are all finite; invalid updates increment a counter and do not overwrite the stored `_trajectory_setpoint`.
3. When the setpoint is missing or stale, the stale branch synthesizes a hold setpoint from the current local position and current yaw, with zero velocity and zero yawspeed. `observe()` then builds finite hover-error inputs for the policy rather than NaN inputs.
4. RAPTOR publishes four active motor controls from the policy output. Channels above `EXECUTOR_CONFIG::OUTPUT_DIM` are deliberately filled with `NAN`; on the quadrotor these are unused `control[4]` through `control[11]`, not active motor failures.

## Observed

`mc_raptor` reported stale setpoints during the run:

```text
trajectory_setpoint turned stale at: -0.012027 -0.014570 -2.368713, yaw: 0.031103
```

The ULOG sanity check reported:

```text
VEHICLE_STATUS_NAV_STATES=4,17,23
RAPTOR_NAV_STATE_23_FIRST_S=41.960
ACTUATOR_MOTORS_TOTAL_NAN_COUNT=144832
ACTUATOR_MOTORS_ACTIVE_0_3_NAN_COUNT=0
ACTUATOR_MOTORS_UNUSED_NAN_COUNT=144832
ARMING_STATES_AFTER_RAPTOR=2
DISARMED_AFTER_RAPTOR=false
```

The total `actuator_motors` NaN count comes entirely from unused control channels `control[4]` through `control[11]` on the quadrotor. Active motor channels `control[0]` through `control[3]` had zero NaNs.

After switching to RAPTOR, local altitude remained bounded:

```text
LOCAL_POSITION_AFTER_RAPTOR_Z_MIN=-2.765
LOCAL_POSITION_AFTER_RAPTOR_Z_MAX=-2.351
ANGULAR_VELOCITY_AFTER_RAPTOR_MAX_ABS_RAD_S=0.343
ATTITUDE_QUATERNION_AFTER_RAPTOR_FINITE=true
```

## Conclusion

The literal "missing setpoint to NaN" oracle did not reproduce because RAPTOR has a stale/missing setpoint guard. In this M0 configuration, naive setpoint starvation is converted into hold fallback before it can become a NaN policy input. The run observed stale setpoint handling, continued armed flight, no active motor NaNs, and no disarm.

This is a useful M0 finding for RQ2: simple setpoint starvation is a negative control for the failure oracle, not a trigger. NaN or instability cases will need stronger M1/M2 perturbations, such as bad-but-finite setpoints, timing and mode-transition edge cases, estimator/state anomalies, extreme trajectories, or search-guided scenario generation.
