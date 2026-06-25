# mc_nn_control GATE-2 Source Review

gate: GATE-2
decision: COMPLETE
date: 2026-06-25
scope: source-only review of `external/PX4-Autopilot/src/modules/mc_nn_control`
no_gate3: true

## Clipping

No observation or error magnitude clipping was found in `mc_nn_control`.

The 15-D input tensor is assigned directly in `PopulateInputTensor()`:
- observation[0..2]: transformed position error, setpoint position minus current position.
- observation[3..8]: first two rows of a transformed 3D attitude rotation matrix.
- observation[9..11]: transformed current linear velocity, not velocity error.
- observation[12..14]: transformed current angular velocity.

There is no RAPTOR-like `max_position_error=0.5` or `max_velocity_error=1.0` equivalent in this module. The only `math::constrain()` in the control loop is for `dt` at `mc_nn_control.cpp:518`, not for observations. The only explicit action clipping is output-side: `RescaleActions()` clamps raw network output to [-1, 1] before converting to normalized motor commands at `mc_nn_control.cpp:412-428`.

## Observation Space

Source and message definitions agree on a 15-D observation:
- Position error: 3 channels.
- Attitude: 6 channels, first two rows of the local rotation matrix.
- Linear velocity: 3 channels.
- Angular velocity: 3 channels.

Unclipped channels:
- Position error is unclipped.
- Linear velocity is unclipped.
- Angular velocity is unclipped.
- Attitude matrix entries are not explicitly clipped; they are bounded only by rotation-matrix geometry and upstream estimator validity.

No previous action or action history channel exists. The network output is 4 motor-force-like values that are rescaled and published to `actuator_motors`.

## Stateful Behavior

The controller is not stateful in the RAPTOR sense.

Evidence:
- Runtime registers only TFLM `FullyConnected`, `Relu`, and `Add` ops at `mc_nn_control.cpp:53-60`.
- The model is loaded into one `tflite::MicroInterpreter`, but the module has no recurrent state member, no hidden-state reset on activation, and no previous action history.
- Persistent module fields such as `_trajectory_setpoint` and `_last_run` are controller bookkeeping, not neural network hidden state.

## Setpoint Handling

Manual-control branch:
- `check_setpoint_validity()` resets the setpoint to current position if age is negative or older than 1.0 s.

Offboard branch, used in GATE-1 because `MC_NN_MANL_CTRL=0`:
- If a `trajectory_setpoint` update arrives, the module copies it only when all three position fields are finite.
- Invalid setpoint updates are ignored, so the previous valid setpoint persists.
- If all three internal setpoint position fields are nonfinite when local position updates, the setpoint is reset to current position.
- In `PopulateInputTensor()`, any nonfinite internal setpoint position component is replaced with a default: x=0, y=0, z=-1.
- There is no offboard setpoint age/staleness timeout equivalent to RAPTOR's stale/missing guard.

Implication: the simple "missing setpoint -> NaN" hypothesis is not supported for position setpoints. Missing or all-NaN setpoints tend to reset or default. Stale offboard setpoints are a better future concern because the last valid finite setpoint can persist indefinitely.

## 0.495 m GATE-1 Question

GATE-1 `tracking_error_max_m=0.495363...` is not evidence of a 0.5 m observation clamp in `mc_nn_control`.

Reasons:
- No source-level position-error clamp exists.
- GATE-1 `neural_control.observation[0..2]` stayed within about [-0.421, 0.442] per axis, while the 0.495 m metric is an Euclidean tracking-error maximum.
- The close value is therefore best explained as hover/switch transient plus the run geometry, not a hidden RAPTOR-like threshold.

## GATE-3 Design Notes For Later

Do not use an absolute safety envelope as the primary GATE-3 metric. GATE-1 hover is already looser than RAPTOR, with RMS tracking error 0.276 m and max 0.495 m. Future GATE-3 should use the D3-style ratio metric: each controller is compared against its own multi-seed nominal baseline, and the signal is the relative degradation of `mc_nn_control` versus the matched classical controller.

Likely future high-value channels, if GATE-3 is later authorized:
- Position-error amplitude, because it is not clipped.
- Linear velocity and angular velocity, because both enter raw.
- Offboard setpoint staleness, because stale finite setpoints persist in this branch.

This report does not design or run any exploit, paired eval, campaign, or GATE-3 test.

## Patch Drift Note

The inherited patch-drift issue for `patches/px4/m2b_state_shim.patch` remains recorded and was not repaired in this turn. It does not affect this GATE-2 source review. If a later GATE-3 needs shim-mediated state perturbations, the shim toolchain should be reconciled first.
