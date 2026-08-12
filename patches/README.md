# Observation patches

These patches add only the evidence surfaces needed by the Family A method.
They are applied to the exact upstream commits in
`config/dependencies.lock.json` and are checked by SHA-256 in
`config/patches.lock.json`.

- `px4/route_observability/route_observability_topics.patch` adds route epoch,
  registration, activation, command-subject, controller, allocator, and writer
  observations without feeding them back into control.
- `px4/route_observability/freshness_observability.patch` extends command
  consumption observations across supported external setpoint levels.
- `px4_ros2_interface/health_reply_gate.patch` provides a deterministic fault
  injection gate for external-mode health replies.

`scripts/setup/prepare_sources.sh` verifies the upstream commit and patch hash
before applying anything. Source trees are detached under ignored `external/`.
