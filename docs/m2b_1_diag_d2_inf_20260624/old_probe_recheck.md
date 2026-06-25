# M2b-1 D2 old Inf timeout recheck

Scope: rechecked the prior 4x high-TWR `velocity_inf` and `attitude_inf` timeouts from
`docs/m2b_inf_probe_4x_20260624/evals/` against the new one-controller D2 rerun.

## Prior velocity_inf timeout

- Prior task log:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_velocity_inf/m1_m2b_inf_probe_4x_20260624_velocity_inf_classical_task.log`
- Prior runner log:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_velocity_inf/m2_eval.log`
- Prior PX4 console:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_velocity_inf/m1_m2b_inf_probe_4x_20260624_velocity_inf_classical_px4_console.log`

The runner timeout was `task node timed out for classical` after `m1_offboard_task.py`
timed out at 160 s. The task log reached `trajectory_start` but did not reach
`mission_end`.

The PX4 console did not show a crash or lockstep stall. It later executed
`listener vehicle_status 1`, `listener vehicle_local_position 1`,
`listener vehicle_angular_velocity 1`, `logger status`, and `shutdown`. The listener
outputs were fresh at PX4 timestamp about 139.4-139.8 s; `vehicle_status` had
`nav_state: 14`, `failsafe: False`, and `vehicle_local_position` / `vehicle_angular_velocity`
were still publishing. Logger status reported `dropouts: 0`, then PX4 printed
`Exiting NOW.`

## Prior attitude_inf timeout

- Prior task log:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_attitude_inf/m1_m2b_inf_probe_4x_20260624_attitude_inf_classical_task.log`
- Prior runner log:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_attitude_inf/m2_eval.log`
- Prior PX4 console:
  `docs/m2b_inf_probe_4x_20260624/evals/m2b_inf_probe_4x_20260624_attitude_inf/m1_m2b_inf_probe_4x_20260624_attitude_inf_classical_px4_console.log`

The runner timeout mode was the same: `task node timed out for classical`; the task
log reached `trajectory_start` but not `mission_end`.

The PX4 console again executed listener commands and clean shutdown. Fresh
`vehicle_status`, `vehicle_local_position`, and `vehicle_angular_velocity` samples
were printed at PX4 timestamp about 139.6-140.0 s. Logger status reported no dropouts,
then PX4 printed `Exiting NOW.`

## New rerun cross-check

The new D2 rerun directory is `docs/m2b_1_diag_d2_inf_20260624`.

- `results.json`: all four one-controller runs (`velocity/attitude` x
  `classical/raptor`) completed with `task_returncode: 0`, `px4_returncode: 0`, and
  `timeout_observed: false`.
- `nonfinite_summary.json`: the requested Inf params were active
  (`M2B_V_PROF: 5` or `M2B_A_PROF: 5`, `M2B_EN: 1`), but no `Inf`/`NaN` reached
  `vehicle_local_position.vx/vy/vz`, `vehicle_attitude.q[0..3]`, or the corresponding
  `raptor_input` fields.

Judgment: the two prior velocity/attitude Inf timeouts are not evidence of PX4 crash
or lockstep stall. They are best classified as harness/task timeout, with a separate
shim-evidence problem: in the fresh rerun, velocity/attitude Inf did not reach the
shared/logged topics that were supposed to carry it.
