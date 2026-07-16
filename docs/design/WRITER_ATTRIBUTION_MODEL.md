# Writer attribution model

Basis: locked PX4 commit `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`.

uORB identifies a topic and optional instance, not the publishing module in
each sample. `PublicationMulti` allocates instances, but an instance is not a
stable writer identity contract. Several modules can advertise
`actuator_motors`; instance 0 therefore does not prove which module wrote a
logged value.

ULog records topic name, multi-instance ID, message fields, and timestamps. It
does not add the uORB publisher's process/module identity. Timestamp equality
or a distinctive value pattern is correlation evidence, not attribution.

For the locked multicopter P0 route:

- `mc_rate_control` publishes `vehicle_torque_setpoint` and
  `vehicle_thrust_setpoint`;
- `control_allocator` subscribes to those topics and publishes
  `actuator_motors`;
- other compiled modules, including direct-controller paths, can also publish
  `actuator_motors`, so source inspection alone does not establish the runtime
  writer.

ROS 2 publisher GIDs can distinguish DDS endpoints inside ROS tooling, but PX4
uORB messages do not carry that GID through the XRCE bridge. The adapter
therefore records a stable producer identity and publish sequence on the ROS
side. Registration replies associate an External Mode name with assigned mode,
executor, and arming-check IDs. Offboard lacks that registration association.

The minimal patch adds a `route_observability` uORB topic with explicit event,
source, topic, writer, subject timestamp, and per-publisher sequence fields.
It records trajectory consumption, the classical multicopter allocator-input
writer, and the final control-allocator motor writer. It is logged, structured,
low overhead, and never read by control code. This is sufficient for the
normal P0 multicopter path, but broader tests must add writer IDs at every
candidate publisher rather than infer them from uORB instance numbers.

The collector reports `UNKNOWN`/`INSUFFICIENT_EVIDENCE` if patched writer
events are absent, sequence continuity is broken, or two writer IDs occur in a
window whose route contract permits only one. It never promotes a mode label or
ULog instance to writer identity.
