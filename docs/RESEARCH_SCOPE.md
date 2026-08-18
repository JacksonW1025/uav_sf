# Research scope

This file is the implementation-facing scope contract. The paper narrative and
research rationale live in [NEW_NARRATIVE_v8.md](NEW_NARRATIVE_v8.md); completed
facts live in [CURRENT_STATUS.md](CURRENT_STATUS.md).

## Core question

The paper studies whether a route-state-guided testing method can expose PX4
authority-handoff problems more effectively than grammar-aware random
generation, deterministic enumeration, and feedback-free state-conditioned
generation under a common budget. Official or handwritten scenarios are a
separately reported practice reference, not a forced budget-equivalent member
of the four-strategy causal comparison.

The object-level obligation is to determine whether a handoff:

- revokes the source route on time;
- completely installs the target route;
- preserves exclusive and continuous actuator authority;
- consumes fresh commands with valid lineage;
- assigns lifecycle ownership correctly;
- reaches the intended successor after completion; and
- installs a complete safe route after a planned failure.

The measurement foundation is established with bounded claims. The target
generation method and its comparative effectiveness are not yet established.

## Core SUT

The required empirical scope is one connected PX4 route system:

- PX4 internal routes;
- Legacy Offboard;
- Dynamic External Mode;
- Mode Executor; and
- internal Hold, RTL, Land, and Recovery.

The tested mechanisms include registration, activation, health, command
consumption, controller/allocator/writer lineage, completion, successor, and
fallback progression.

The upper mission, planning, behavior, and companion stack is not the SUT. It
provides realistic seeds and execution context, demonstrates reachability, and
replays representative findings in full-stack closed-loop simulation.

## Required method scope

The final method must use a semantic state larger than route identity alone.
It includes route epoch, authority ownership and lineage, lifecycle phase,
registration and activation, health and freshness, successor/fallback
progress, motion or mission context, and bounded action history.

The generator must choose both lifecycle action sequences and timing in a
closed loop. The current timing-selection implementation is a prototype, not
the completed paper method.

## Optional external validation

Additional route mechanisms, PX4 revisions, autopilots, airframes, HITL, and
real flight may strengthen external validity. The core claim must stand on the
PX4 scope above and full-stack SITL; optional systems cannot become a hidden
completion dependency.

## Non-goals

- modifying PX4 control logic;
- building runtime protection or automatic recovery;
- treating the upper autonomy stack as the defect target;
- equating every research-contract violation with a PX4 defect or security
  vulnerability; or
- claiming cross-system generality without corresponding evidence.

## Claim boundary

Static validation and unit tests establish repository consistency, not flight
behavior or method effectiveness. Every new empirical claim requires a new
preregistered plan, an attested execution environment, admissible evidence,
and a denominator separate from completed studies.
