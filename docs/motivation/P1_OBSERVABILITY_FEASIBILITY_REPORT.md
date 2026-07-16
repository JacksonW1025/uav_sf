# P-1 route observability feasibility

Locked PX4: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.

## Result

All 14 route fields have an explicit status and source/collector contract:

| Status | Count | Fields |
|---|---:|---|
| DIRECT | 4 | declared mode, registration state, actuator output, failsafe state |
| DERIVED | 7 | authority source, setpoint level/topic/freshness, enabled/bypassed modules, fallback target |
| INSTRUMENTATION_REQUIRED | 3 | producer identity, allocator input, actuator writer |
| UNOBSERVABLE | 0 | — |

The exact source paths, symbols, messages, timestamp sources, collection
methods, confidence, and limits are in `docs/design/OBSERVABILITY_MATRIX.tsv`.

## Feasible collection

`route_trace_collector.py` reduces ROS/ULog signals into the versioned route
trace schema. Producer publications and PX4 consumption are separate event
types. `actuator_writer_collector.py` accepts attribution only from explicit
instrumentation. The route state is reconstructed from `vehicle_status`,
registration replies, `vehicle_control_mode`, setpoint receipt/consumption,
failsafe flags, allocator/writer events, and actuator output.

The three native gaps have one minimal PX4 patch. It adds a logged structured
topic at the multicopter trajectory consumer, classical rate-controller
allocator input, and control-allocator motor output. It applies cleanly to the
locked commit and does not modify a control value or decision. It intentionally
does not cover every PX4 vehicle/controller family.

## Risks

PX4 boot/uORB/ULog timestamps are directly orderable inside one boot. ROS,
DDS-receive, simulation, and wall clocks require explicit bridge segments.
Accelerated simulation invalidates wall-time flight deadlines. A time-sync
configuration is not proof of convergence.

Native uORB and ULog do not preserve writer identity. ROS publisher identity is
also lost at the XRCE-to-uORB boundary. P0 is constrained to one declared ROS
producer per route, records that producer locally, and uses the PX4 consumption
event to distinguish publication from influence. Multi-producer Offboard tests
remain outside the gate.

## P0 readiness and later-oracle risk

The static observability design is sufficient in scope for the three normal P0
flows only after the patched PX4 and official ROS examples compile and the
collector/schema tests pass. Gate status is machine-readable in
`experiments/motivation/p1_gate_result.json`; this report does not predeclare a
pass.

Later oracles must treat missing writer/consumer events, broken sequences,
clock-bridge resets, and incomplete module flags as unknown evidence. Coverage
must be expanded before direct-actuator, VTOL, rover, concurrent-producer, or
Family B experiments.
