# Route model

A control route is the runtime path by which authority becomes actuator output. The model deliberately separates the control plane (registration, mode requests, declared state, fallback selection) from the data plane (actual producers, messages, module bypasses, allocator input, and final writer).

For an observation time `t`, represent a route as:

```text
R(t) = <declared_mode,
        registration_state,
        authority_source,
        producer_identity,
        setpoint_level,
        setpoint_topic,
        message_freshness,
        enabled_modules,
        bypassed_modules,
        allocator_input,
        actuator_writer,
        actuator_output,
        failsafe_state,
        fallback_target>
```

## Transition obligations

For a declared replacement `R_A → R_B`, evaluate four independent obligations:

- **Revocation:** every authority-bearing producer, subscription, writer, and bypass unique to `R_A` stops influencing the vehicle within its allowed deadline.
- **Installation:** every required element of `R_B` becomes present, fresh, and mutually consistent.
- **Exclusivity and continuity:** no forbidden overlap permits competing writers, and no forbidden gap leaves the actuator path without a valid owner/input.
- **Recovery:** after loss/rejection/failure, the selected fallback route is installed as a complete path, not merely declared.

## Handoff versus update

A handoff changes at least one authority-bearing route element: authority source, producer identity, setpoint level, enabled/bypassed module path, allocator input, or actuator writer. A new waypoint, trajectory segment, or value published by the same producer on the same path is an in-route update and must not be counted as a handoff.

## Time and evidence

Observations must record timestamp domain and synchronization assumptions. Control-plane declarations and data-plane events can use different clocks; overlap/gap conclusions require a justified mapping. Missing writer attribution or freshness evidence yields `unknown`, not a pass.

The canonical field-by-field feasibility inventory is `OBSERVABILITY_MATRIX.tsv`. Concrete profiles follow `ROUTE_PROFILE_SCHEMA.md`.
