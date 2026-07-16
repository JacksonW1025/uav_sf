# P0 official handoff baselines

P0 is the first low-risk runtime probe after the machine-readable P-1 gate
reports `PASS`. It is a deterministic normal-flow baseline, not a fault
campaign and not evidence that every route-transition oracle is complete.

## Preconditions

1. `./scripts/setup/bootstrap_family_a.sh` has completed successfully.
2. `experiments/motivation/p1_gate_result.json` has status `PASS`.
3. The locked PX4 observation patch is applied in the generated
   `external/PX4-Autopilot-route-observability` worktree.

## Scenarios

```bash
./docker/run.sh ./scripts/probes/run_p0_scenario.sh offboard RUN_ID
./docker/run.sh ./scripts/probes/run_p0_scenario.sh external RUN_ID
./docker/run.sh ./scripts/probes/run_p0_scenario.sh executor RUN_ID
```

- `offboard`: Internal Takeoff → Offboard hover → 0.5 m/s straight line →
  explicit release → RTL/Land.
- `external`: Internal Takeoff → registered Dynamic External Mode hover →
  0.5 m/s straight line → `ModeCompleted` → RTL/Land.
- `executor`: executor-controlled Takeoff → owned registered mode → RTL →
  Wait Until Disarmed.

The External Mode receives its mode ID from a successful registration reply.
Selecting that assigned ID activates a real `ModeBase` implementation with a
declared trajectory setpoint type; it is not an unregistered external
`nav_state` request.

The harness does not kill a flight process, decouple heartbeat/data, inject a
DDS or failsafe fault, introduce RC takeover, command a large attitude/high
speed, or randomize inputs. Infrastructure is terminated only after normal
landing, disarming, PX4 shutdown, and ULog closure.

## Outputs

Raw ULogs and process logs remain under ignored `runs/p0/<run_id>/raw/`.
Tracked evidence is limited to:

```text
data/processed/p0/<run_id>/route_trace.jsonl
data/processed/p0/<run_id>/route_summary.json
```

The trace preserves PX4/ULog microseconds and ROS node nanoseconds as distinct
clock domains. The summary never subtracts one domain from the other; a clock
bridge is required for cross-domain overlap/gap calculations.
