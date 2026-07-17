# P3 Heartbeat–Setpoint Decoupling

P3 completed 24 accepted deterministic cases: two route objects, four channel
combinations, and three repeats per object/combination. The complete accepted
matrix is [experiment_matrix.tsv](../../experiments/probes/p3/experiment_matrix.tsv).

## Independent controls

Offboard independently gates `OffboardControlMode` proof-of-life and
`TrajectorySetpoint`. Dynamic External Mode independently gates arming-check
health replies and its trajectory-setpoint update. The External process stays
alive throughout the fixed channel observation window; no process signal is
used to create a P3 combination. Producer shutdown begins only after the
observation window closes.

Each accepted case uses stable hover, q4 observation, a 15 s pre-switch window
for the preregistered 20-sample clock minimum, and a four-second channel
window. Every accepted bridge is `VALID`. Health replies are restored during
External deactivation so the later unregister handshake can complete.

## Results

| object | heartbeat / health | setpoint | automatic fallback | Route Oracle result counts |
|---|---|---|---:|---|
| Offboard | ON | ON | 0/3 | 3 PASS |
| Offboard | ON | OFF | 0/3 | 2 PASS, 1 UNKNOWN |
| Offboard | OFF | ON | 3/3 | 3 PASS |
| Offboard | OFF | OFF | 3/3 | 3 PASS |
| Dynamic External | ON | ON | 0/3 | 1 PASS, 2 UNKNOWN |
| Dynamic External | ON | OFF | 0/3 | 1 PASS, 2 UNKNOWN |
| Dynamic External | OFF | ON | 3/3 | 3 PASS |
| Dynamic External | OFF | OFF | 3/3 | 3 PASS |

All 24 channel-behavior verdicts are PASS and clock-valid. The decisive input
for route retention is proof-of-life/health, not continued setpoint messages:

- with heartbeat or health ON, the source route remained selected for the
  complete channel window even when setpoints stopped;
- with heartbeat or health OFF, PX4 installed fallback in all repeats even
  when setpoints continued.

Across the 24 cases, 110 Oracle clauses are PASS and 10 are UNKNOWN; no clause
is a violation. The five overall `UNKNOWN` Oracle results occur in deliberate
retention cases whose later explicit cleanup transition has a `BOUNDED`
critical writer window. Oracle 0.2 correctly refuses to exclude overlap below
that local resolution. The channel-window retention/fallback observation is
separate, complete, and does not convert those Oracle clauses to PASS.

All automatic fallback cases have zero post-revocation old-epoch consumption
and writer events. Clock uncertainty is 29.1–94.8 ms, maximum altitude change
reported as loss during the channel window is 0.155 m, and maximum tilt is
0.24 degrees. Angular-rate peak is `UNKNOWN` because the locked DDS topic is
not published.

## Exclusions and claim boundary

Failed raw attempts include the recurring SITL/Gazebo mutex abort, one
insufficient-sample bridge, and two `DEGRADED` bridges. The watchdog classified
PX4 exits as environment failures and stopped those attempts immediately.
No failed or degraded run appears in the accepted 24-row matrix, and no
measurement threshold was relaxed.

P3 demonstrates deterministic channel decoupling for the tested configurations
only. It is not a probability estimate, full external-framework integration,
or fuzzing result.
