# Writer attribution model

Basis: locked PX4 `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.

uORB topic instance is not writer identity. `PublicationMulti` assigns instances, but multiple modules can advertise `actuator_motors`, and instance allocation can change with startup order. ULog preserves topic, multi-instance, fields, and timestamps; it does not add module identity.

The source inventory found nine publisher/declaration families. Four are compiled into `px4_sitl_default`: `control_allocator`, `rover_ackermann`, `rover_differential`, and `rover_mecanum`; all four are instrumented. The x500 P0 runtime candidate is `control_allocator`. Five stable IDs are reserved for non-default or test families (`mc_raptor`, `mc_nn_control`, `uavcannode`, `spacecraft`, and mixer tests) but those sources are not instrumented by this patch. Their selection therefore produces `INSUFFICIENT_COVERAGE`, never an inferred writer.

Each publisher emits an observation event containing writer ID, source/topic ID, uORB subject timestamp, profile, expected period, and a publisher-local monotonic sequence. BASELINE is about 10 Hz. TRANSITION is configured for 8 ms and measured at about 122 Hz. The logger records all topic instances with interval zero.

`actuator_writer_collector.py` returns exactly one of:

- `EXCLUSIVE`: all configured candidates are instrumented, a transition window exists, sequences are continuous, rate/coverage is adequate, there is no observation hole, and only one writer is observed;
- `COMPETING_WRITERS`: multiple stable writer IDs occur in one exclusivity window;
- `INSUFFICIENT_COVERAGE`: candidate instrumentation, rate, transition, or window coverage is missing;
- `SEQUENCE_GAP`: publisher sequence proves logger loss;
- `NO_EVIDENCE`: no writer observations exist.

The Phase A.1 P0 traces observe only `control_allocator`, but contain writer sequence gaps and post-disarm logger holes. Their status is `SEQUENCE_GAP`; they do not prove whole-window writer exclusivity.

Finally, a writer module may be shared by old and target routes. Even perfectly identifying `control_allocator` cannot attribute a post-transition motor publication to one upstream route. Route Oracle v0 therefore requires a `route_epoch_id` for old-writer revocation; absent that causal identifier, revocation/recovery writer claims are `UNKNOWN` rather than treating continued allocator output as old-route residue.
