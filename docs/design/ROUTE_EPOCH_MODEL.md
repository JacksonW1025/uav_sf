# Route Epoch Model

Phase A.2 separates route identity from module identity. A shared module such
as `mc_rate_control` or `control_allocator` can execute for several routes, so
its name alone is not evidence that an old route still owns the data plane.

## Identities

- `route_epoch_id` is a PX4-boot-local monotonically increasing identifier.
  PX4 increments it whenever the final selected navigation route changes.
- `route_activation_id` identifies each activation of one registered External
  Mode. Re-activating the same mode creates a new activation and route epoch.
- `producer_session_id` identifies one continuous Offboard producer session,
  from prestream through activation and release or loss.
- `registration_instance_id` identifies one successful lifetime of a ROS
  external component registration.

IDs are scoped to one PX4 boot or one producer process as appropriate; they
are not global database identifiers. Ordinary trajectory updates do not create
an epoch. A route can receive a new epoch even when a registration ID is
reused, and the same writer in two epochs represents two distinct influences.

## Ordering and attribution

PX4 publishes `EVENT_ROUTE_EPOCH_CHANGED` after final route selection and
before data-plane observations for the new route. Each observation carries the
current `route_epoch_id`. The collector also defines epoch-change precedence
when an epoch event and data event have the same PX4 timestamp. Attribution
never crosses a boot or clock-bridge segment.

The epoch event records the previous and new navigation state, change source,
registration mode ID, executor-in-charge ID, and armed state. It is emitted by
an observation-only patch and does not alter selection, failsafe, controller,
setpoint, or actuator behavior.

## Legacy traces

The 1.1-to-1.2 migrator writes all four identities as `null` when they cannot
be derived. It does not synthesize epochs from writer names or navigation-state
retention. Phase A.1 summaries are marked as superseded by Phase A.2
measurement.
