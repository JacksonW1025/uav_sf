# P0 official handoff baseline report

Run date: 2026-07-16. PX4 `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`, px4_msgs `18ecff03041c6f8d8a0012fbc63af0b23dd60af1`, and px4-ros2-interface-lib `c3e410f035806e8c56246708432ded09c976434b`.

## Phase A.1 reruns

| Scenario | Run ID | execution_status | route_verdict | Trace events | Final-writer rate | Writer coverage/status |
|---|---|---|---|---:|---:|---|
| P0-A Offboard | `p0a_offboard_phase_a1_20260716T0710` | PASS | UNKNOWN | 8,303 | 121.71 Hz | 99.58%; `SEQUENCE_GAP` |
| P0-B Dynamic External Mode | `p0b_external_mode_phase_a1_20260716T0720` | PASS | UNKNOWN | 8,816 | 121.94 Hz | 99.60%; `SEQUENCE_GAP` |
| P0-C Mode Executor | `p0c_executor_phase_a1_20260716T0730` | PASS | UNKNOWN | 8,152 | 121.61 Hz | 99.48%; `SEQUENCE_GAP` |

`execution_status=PASS` means the intended Takeoff/external-control/RTL/disarm normal flow completed. It does not imply the route contract passed. Route Oracle 0.1 reports installation `PASS` for the selected target edge, but revocation, exclusivity, continuity, and recovery remain `UNKNOWN` where evidence lacks a cross-domain bridge, route epoch, continuous sequence, or post-disarm logger coverage.

All three traces observe `mc_rate_control` at allocator input and `control_allocator` at final actuator output. This identifies observed samples and the current x500 candidate, but does not prove whole-window exclusivity. No competing stable writer ID was observed. Missing samples are not evidence that no other writer ran.

## Schema correction

New traces use canonical schema 1.1. Producer records now carry, for example, `behavior_phase="straight_line"` and `setpoint_level="velocity"`. External Mode uses velocity trajectory setpoints; Offboard level is derived from `OffboardControlMode` and finite trajectory fields.

The three earlier compact P0 traces were migrated from 1.0 to 1.1 with `scripts/tracing/migrate_route_trace_v1_0_to_v1_1.py`. Their original SHA-256 hashes are retained in migration reports. Incorrect phase-like values were moved to `behavior_phase`; otherwise uncertain old levels became `unknown`. The old summaries are marked `superseded_measurement_v1` and retain `route_verdict=UNKNOWN`.

## Measurement limits

TRANSITION meets the frequency gate but is not per-publication complete. P0-A lost 19 of 4514 expected final-writer observations, with a maximum recorded writer gap of 20 ms. Post-disarm logger stop/start also creates observation holes. Therefore P0 exclusivity and continuity cannot be `PASS`; the minimum recorded gap scale is 20 ms, while shorter missed overlap/gap remains possible inside sequence holes.

Compact 1.1 traces, summaries, and oracle results are under `data/processed/p0/`. They retain every final-writer event and one in four allocator-input events; each summary records that policy. Raw ULogs, including the complete allocator-input stream, and logs remain ignored under `runs/p0/`.
