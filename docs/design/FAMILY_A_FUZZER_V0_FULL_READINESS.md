# Family A Fuzzer v0 full execution readiness

The formal stage remains named **Family A Fuzzer v0** in repository assets and
is also called **Family A State-Space Evaluator v0** for this readiness task.
Both names refer to the same local PX4 SITL qualification design.

## Environment boundary

The sole formal environment is
[`containers/family_a_fuzzer_v0`](../../containers/family_a_fuzzer_v0/README.md).
It starts from the Docker Official ROS Jazzy image at an OCI index and native
`linux/arm64` manifest digest, installs exact apt/ROS and hash-locked pip
packages, and builds PX4, its required Gazebo target, `px4_msgs`,
`px4-ros2-interface-lib`, Micro-XRCE-DDS-Agent, every Family A adapter
including C1, collectors, Oracles, safety, evidence, accounting, strategies,
and the unique runner in one image-local workspace.

The entrypoint clears all incoming ROS prefixes before sourcing only
`/opt/ros/jazzy` and `/opt/family_a/workspace/ros/install`. Formal wrappers do
not pass host ROS environment variables or mount a host ROS workspace.

## Call graph and safety

Each of the six frozen V0-P slots resolves the same ordered lifecycle from
pushed authorization and prelaunch registration through container/process
preflight, collector and supervisor readiness, scenario launch, live
supervision, collection close, Oracle invocation, evidence staging, cleanup,
classification, append-only closure, and final compact-evidence sealing.
Slot-specific freshness, successor, and linearization nodes retain explicit
`NOT_APPLICABLE` markers instead of silently becoming PASS.

The supervisor starts before the scenario and monitors heartbeat, timeout,
collector failure, clock progression, PX4 abort, finite data, physical
boundaries, ground contact, route epoch, writer/controller lineage, and
terminal Land/Disarm. A stop targets only the attempt process group.

## Authorization and accounting

Authorization avoids Git self-reference: the final manifest locks every input
file and predecessor commit, while the caller supplies the identity-lock commit.
The runner proves that supplied commit is in exact pushed `origin/main` ancestry
and contains the manifest's exact blob.

Formal registration writes a separate tracked prelaunch record. Execute
requires the exact pushed registration commit before writing the first
hash-chained attempt event. Launched attempts consume the six-attempt budget;
prelaunch rejections are retained without consuming it; closed streams cannot
reopen; and aggregate ledgers are derived from the event streams.

## Readiness-only boundary

This task uses static, fixture, mock-process, read-only container, and clean
clone validation only. Qualification authorization, if independently granted,
means a later separate task may begin; it is not a qualification result.
Comparison arms remain implemented but unauthorized, and neither state-aware
gain nor full-method effectiveness is established.
