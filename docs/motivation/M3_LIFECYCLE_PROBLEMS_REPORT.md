# M3 external-mode lifecycle problems report

## Result

The matrix contains 12 pinned PX4 or px4-ros2-interface-lib issues, pull requests, and commits. It separates control-plane state (registration, ownership, mode intention, scheduling, activation) from data-plane state (setpoint configuration, consumption, and route output), and does not infer a physical failure where the source reports only a lifecycle symptom.

Classification at the dependency lock is:

- four historical problems fixed in the locked interface lineage;
- two locked-version design semantics/guards;
- one coordinated locked protocol design change;
- one open issue that remains applicable or cannot be excluded at the lock;
- one open scheduling issue that remains or cannot be confirmed;
- two issues whose relevance to the exact lock cannot be established;
- one PX4 Offboard/RTL report closed stale without a fixing commit.

## High-value findings

`executor/disarm mode restoration`: commit `7b0cc05...` added the explicit “do not reactivate while disarmed” guard. Therefore a retained numeric nav state after disarm is not itself evidence that `onActivate()` ran or that the data plane resumed. P0-D treats activation, consumption, and writer evidence separately.

`replacement/executor ownership`: PX4 issue 25707 documents that an executor-owned external replacement of internal RTL is not supported by the current mode-intention/failsafe layering. Interface PR 160 now rejects the combination. The oracle should return `NOT_APPLICABLE` for a test that violates this design guard, not label the rejection a route failure.

`unregister before shutdown`: PR 175 moved unregistration before ROS shutdown because the old order could not publish `/fmu/in/unregister_ext_component`. The locked interface contains the fix. P0-D observed one request, but no direct registry-slot removal evidence, and teardown subsequently exposed a timeout exception; the report therefore does not claim clean slot removal.

`registration while armed`: the audited sources constrain registration and activation ordering, validate registration freshness, and prevent some unsupported combinations. No matrix row establishes that arbitrary registration while armed is safe; installation evidence must include the exact registration reply, activation, setpoint configuration, and consumption sequence.

`replacement and Offboard setpoints`: issue 19005 reports trajectory input affecting RTL but was closed stale with no pinned fix. It remains a useful revocation seed, not proof of a bug in locked PX4. Issue 206/PR 207 is stronger: premature setpoint-type activation caused newer PX4 to reject intended rate setpoints, and the locked interface includes the exact fix `c6a0f742...`.

## Oracle implications

- Registration success without a live boot identity is insufficient (issue 201).
- Mode/executor selection without fresh setpoint configuration is insufficient (issue 206).
- Shared final writers need a route-epoch identifier; writer identity alone cannot prove revocation.
- Process exceptions and unregister requests must be followed by fallback installation and fresh target consumption.
- Design-rejected ownership combinations are not valid failure seeds.

No matrix row claims that a reported symptom persists in the lock unless an exact fixing commit is absent and the open source still applies. Full row-level evidence is in [LIFECYCLE_ISSUE_MATRIX.tsv](LIFECYCLE_ISSUE_MATRIX.tsv).
