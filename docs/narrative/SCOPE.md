# Current research scope

The current topic is **Testing Route-Replacing Authority Transitions in PX4**.

The central question is whether a declared transfer from Route A to Route B is reflected by the complete runtime control path:

1. the old path is revoked promptly;
2. the new path is completely installed;
3. the transition window remains exclusive and continuous;
4. the safe path is completely restored after failure.

For executor-owned routes, the declared handoff contract also includes the
Successor Progression Contract: the registered lifecycle owner and executor
owner must receive completion and request/install the expected successor.
Route Oracle checks control-path revocation/installation; Successor Oracle
checks ownership, completion delivery, and successor progression. The two
contracts are complementary and are not substituted for one another.

## Subject families

**Family A — primary reality-facing subjects**

```text
PX4 Internal Route
↔ ROS 2 Offboard
↔ Dynamic External Mode
↔ Internal Fallback / RTL / Land / RC takeover
```

**Family B — representative deep-route case**

```text
PX4 Classical Cascade
↔ Registered Learned Controller
↔ Classical Fallback
```

Existing mc_nn/RAPTOR/classical results are legacy evidence and future cross-family validation material. They are not automatically evidence about Family A.

## Current sequence

```text
Repository recovery and route observability (complete)
→ P5 v6 bounded differential campaign (complete and frozen)
→ Motivation Case 1: Issue #162 successor failure (complete and frozen)
→ Current-version External Mode setpoint freshness bounded probe (current)
→ continuation decision at the freshness Pilot Gate
```

The current authorization is limited to the four-cell, twelve-accepted-run
freshness pilot for Dynamic External Mode Trajectory, Attitude, and Rate
setpoints. It does not authorize a 54-run matrix, generic mode fuzzing, a new P5
campaign, direct-actuator flight, Aerostack2, rapid-restart/concurrency work, or
Stateful Fuzzer v0. Family B remains future deep-route validation material. No
current-version freshness defect is claimed before the pilot is adjudicated.
