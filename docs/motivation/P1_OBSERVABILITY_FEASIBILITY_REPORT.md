# P-1 route observability feasibility

Locked PX4: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.

## Phase A.1 correction

The prior feasibility statement was too strong. The old patch rate-limited allocator/writer observations with a 100 ms elapsed-time check, which is about 10 Hz, not 100 Hz. It also referenced `RouteObservability.msg` from CMake without carrying the new-file patch segment. Phase A.1 recovered the used message definition, assigned stable IDs from source/generated-header/ULog evidence, and made the patch self-contained.

The final profiles are:

| Measurement | BASELINE evidence | TRANSITION evidence |
|---|---:|---:|
| expected period | 100 ms | 8 ms |
| measured final-writer rate | 10.00 Hz | 121.71 Hz |
| final-writer actual/expected events | 386/386 | 4495/4514 |
| maximum recorded final-writer gap | 100 ms | 20 ms |
| final-writer sequence loss | 0 | 19 |
| all-observation coverage | 47.00% (old unthrottled consumer was heavily lost) | 99.64% |
| mean/max recorded CPU load | 36.30% / 42.00% | 26.71% / 30.00% |
| ULog size | 9,114,735 bytes | 9,022,240 bytes |

CPU and ULog figures come from different short normal-flow runs and are descriptive, not a controlled causal overhead estimate. The transition frequency gate passes because final-writer rate is ≥100 Hz. Per-publication completeness fails, so exclusivity and continuity remain unknown where sequences or logger segments have holes. The minimum defensible recorded writer-gap scale is 20 ms; shorter missed overlap/gap cannot be excluded.

## Coverage

The patch instruments every `actuator_motors` candidate compiled into `px4_sitl_default`, and all current x500 P0 candidates. It does not instrument non-default neural/RAPTOR/UAVCAN/spacecraft/test writers. The machine-readable inventory makes this a precondition rather than an assumption.

The canonical 1.1 trace separates producer-side behavior phase from setpoint level, keeps ROS and PX4 clocks separate, and records observation profile/sequence. The strengthened writer collector rejects exclusive attribution for missing candidates, sequence discontinuity, inadequate frequency, absent windows, or holes. Route Oracle v0 uses `UNKNOWN` for missing clock bridges and route-epoch causality.

## Feasibility conclusion

The infrastructure is feasible for deterministic normal-flow execution and high-rate observation, but the measured logger loss prevents full-window exclusivity/continuity proof in the current P0 runs. It is not yet sufficient for direct-actuator, non-default writer families, or cross-domain latency without added instrumentation and a valid clock bridge.
