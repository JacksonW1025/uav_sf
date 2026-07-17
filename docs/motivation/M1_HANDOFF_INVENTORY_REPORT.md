# M1 handoff inventory report

## Scope and method

The inventory pins 26 source-level transitions to exact commits: the MAVSDK C++ Offboard example, three px4-ros2-interface-lib example families, and three public autonomy frameworks (Aerostack2, MRS UAV System, and KR Autonomous Flight). Nineteen rows are classified as true route-replacing authority transitions and seven as trajectory updates, task-state transitions, shared/partial authority, or terminal gating.

This is a purposive source audit, not a representative industry sample. Counts describe only the pinned code paths in `HANDOFF_INVENTORY.tsv`; they do not estimate how often handoffs occur across UAV systems.

## Counts and transition types

| Pinned source | Inventory rows | True route handoffs | Non-handoffs |
|---|---:|---:|---:|
| MAVSDK C++ Offboard example | 9 | 8 | 1 |
| px4-ros2 mode executor | 4 | 3 | 1 |
| px4-ros2 multi-mode executor | 2 | 2 | 0 |
| px4-ros2 RTL replacement | 1 | 1 | 0 |
| Aerostack2 | 4 | 2 | 2 |
| MRS UAV System ROS2 | 3 | 2 | 1 |
| KR Autonomous Flight | 3 | 1 | 2 |
| **Total** | **26** | **19** | **7** |

Among the 19 classified handoffs, 12 are programmed task/phase boundaries, three are operator-or-mission admissions, one is a direct mode request, one combines a mode request with possible failsafe selection, one is an emergency, and one is a process/API failure fallback. The sampled true-handoff rows contain no independently verified cancel-to-new-route or manual-takeover edge. That absence is a gap in these pinned examples, not evidence that those triggers are rare.

Source routes include internal Takeoff/Hold, Offboard at position/velocity/attitude levels, registered External Modes, and active autonomy-framework companion routes. Target routes include internal Hold/Land/RTL, another registered External Mode, a replacement RTL mode, and PX4-configured failsafes. External-to-external handoffs in the multi-mode executor are especially useful because a stable PX4 mode family is insufficient to identify the changing producer.

## What is not a handoff

- MAVSDK north/south/up/down changes retain the same Offboard producer and controller graph.
- Aerostack2 go-to/follow-path and action cancellation can change task behavior while retaining its platform Offboard route.
- MRS tracker/controller selection can change shared or partial authority inside one companion route.
- KR planner replanning and its LandTracker transition do not prove a PX4 mode or writer replacement.
- `waitUntilDisarmed` is terminal gating after RTL, not a new authority route.

These rows remain in the inventory so later seed generation does not inflate handoff counts with ordinary state-machine edges.

## Seed priorities

1. External-to-internal completion and failure edges: Offboard/External Mode → Hold/RTL/Land.
2. Internal-to-external admission after Takeoff, with fresh setpoint configuration and first-consumption checks.
3. External A → External B scheduled edges, because producer identity can change while the final allocator writer does not.
4. Replacement RTL → internal RTL fallback, excluding the unsupported executor-owned replacement combination.
5. Real-workload emergency and companion-loss edges from Aerostack2 and MRS.
6. Cancel and human-takeover traces acquired from a real workload, since the current source sample does not verify those as route replacements.

The exact source, trigger, source/target route, setpoint level, fallback, and bounded classification are in [HANDOFF_INVENTORY.tsv](HANDOFF_INVENTORY.tsv).
