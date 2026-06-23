# M0 Oracle Sanity: Missing Setpoint to NaN

## Setup

- Simulator: `px4_sitl_raptor_sih` with `sihsim_quadx`.
- RAPTOR mode: external mode `mode_id 23`, selected via MAVLink `MAV_CMD_DO_SET_MODE`.
- Internal reference: `MC_RAPTOR_INTREF=0`.
- No ROS 2 offboard task node or external setpoint stream was used.
- ULOG: `docs/m0_run.ulg`.

## Expected Behavior

Guarded RAPTOR treats a stale or missing `trajectory_setpoint` as a hold command after the setpoint timeout. The expected result for the literal missing-setpoint sanity check is therefore hover/hold, not NaN.

If a learning controller emits NaN on an active motor command, PX4's direct actuator path maps that to disarmed output. The observable oracle signal is active `actuator_motors` NaN together with an unexpected disarm.

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

The literal "missing setpoint to NaN" oracle did not reproduce on guarded RAPTOR. The run observed stale setpoint handling, continued armed flight, no active motor NaNs, and no disarm.

This is a useful M0 finding: simple setpoint starvation is not enough to expose the NaN/disarm failure path in current RAPTOR. NaN or instability cases will need later search-guided scenario generation; that belongs to M2+, not this M0 run.
