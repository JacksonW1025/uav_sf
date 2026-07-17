# P0-D post-disarm re-entry report

Official bounded attempt: `p0d_post_disarm_phase_a1_20260716T0755`.

## Result

- execution status: `FAIL` (the required rearm/second observation window did not complete)
- route verdict: `UNKNOWN`
- bounded terminology: **post-disarm nav-state retention** followed by **insufficient evidence** for re-entry

The first flight completed Takeoff → External Mode 23 → Complete → RTL → disarm. At disarm, nav state was 23. During the retained post-disarm observation and shutdown sequence, observed disarmed nav states were 23 and 5. The External Mode logged one `onActivate`, one `onDeactivate`, and eight sampled setpoint log records (the log is intentionally 1 Hz, not every publication). PX4 trace contains the corresponding consumption and writer streams.

After five seconds, the orchestrator signalled the actual mode executable directly rather than its `ros2 run` wrapper. The probe observed one `/fmu/in/unregister_ext_component` request. It did not observe direct registry-slot removal evidence. The mode teardown then threw a timeout exception after logging `Unregistering`; this is a control-plane symptom, but the available record does not establish whether the request removed every registry slot.

After the three-second wait, the probe issued rearm commands. PX4 repeatedly denied arming with a system-health failure, so no second armed state, internal Position observation window, or final disarm was obtained. The attempt ended in state `REARM`; no second `onActivate` occurred.

## Evidence boundary

The trace does **not** show data-plane residue as defined for this study. There is no evidence that an old setpoint was consumed after release, that an old route-attributed writer continued, that rearm automatically selected the external route, or that an old configuration became active without re-admission. Continued `control_allocator` output is shared final-writer behavior and lacks `route_epoch_id`, so it cannot be assigned to the old route.

The numeric 23 observed at disarm is therefore described only as post-disarm nav-state retention. The later 5 and unregister request are consistent with control-plane progression, but clean re-entry is unproven because rearm failed. Whether the arming denial reflects control-plane residue, a separate health condition, or teardown timing remains insufficient evidence.

PX4 logger closes at disarm and opens a new ULog on rearm. The collector now accepts repeated `--ulog` segments and merges them in one boot-time domain. This attempt produced only the pre-disarm segment because rearm never succeeded; the earlier diagnostic that selected only the last ULog is superseded and remains ignored.
