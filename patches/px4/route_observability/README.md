# PX4 route-observability patch

Base PX4 commit: `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`, read from `config/dependencies.lock.yaml` by every setup/check script.

`route_observability_topics.patch` is self-contained. It creates `msg/RouteObservability.msg`, registers it in `msg/CMakeLists.txt`, adds an observation-only publisher helper, configures the logger for all topic instances with interval `0` (the PX4 logger API uses milliseconds; zero records every update), and instruments:

- `mc_pos_control` trajectory-setpoint consumption;
- `mc_rate_control` allocator input;
- `control_allocator`, `rover_ackermann`, `rover_differential`, and `rover_mecanum` `actuator_motors` writers compiled into `px4_sitl_default`.

The complete source inventory and stable writer IDs are in `docs/design/ACTUATOR_WRITER_INVENTORY.tsv`. Writers not compiled into the default image retain IDs in the message definition, but are deliberately uninstrumented; selecting one makes the writer oracle return `INSUFFICIENT_COVERAGE`.

## Profiles

| Profile | Compile setting | Expected publisher period | Intended use |
|---|---|---:|---|
| BASELINE | default | 100 ms (about 10 Hz) | low-overhead, long state observation |
| TRANSITION | `-DROUTE_OBSERVABILITY_TRANSITION=1` | 8 ms (measured about 122 Hz) | handoff windows, sequence/overlap/gap evidence |

The 8 ms setting accounts for the 4 ms scheduling quantization observed in SITL. The official short probe measured the final writer at 121.71 Hz. Publisher-local sequences remain monotonic. ULog retained 4495 of 4514 expected writer events (99.58% coverage), so frequency passes the Phase A.1 ≥100 Hz gate but sequence gaps prevent an exclusivity or continuity `PASS`. The largest recorded writer-event gap was 20 ms; because missed sequence elements exist, gaps shorter than that cannot be excluded in the affected windows.

The helper is never read by control code. The patch changes no setpoint, control output, controller state, mode arbitration, work-queue interval, or control branch, and emits no console output.

Use:

```bash
scripts/setup/prepare_observability_px4.sh --profile TRANSITION --build
scripts/validation/rebuild_observability_patch.sh
```

The first command prepares the ignored detached working tree. The integration validator creates a separate temporary detached worktree, applies only the tracked patch, verifies the new message and `git diff --check`, builds `px4_sitl_default`, and removes the temporary worktree.
