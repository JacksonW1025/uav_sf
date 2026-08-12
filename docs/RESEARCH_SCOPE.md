# Research scope

## Research question

This project tests route-replacing authority transitions in PX4. A transition
is correct only when the previous runtime route is revoked on time, the next
route is fully installed, actuator authority stays exclusive and continuous,
the consumed command is fresh and attributable, lifecycle ownership is
correct, completion reaches the intended successor, and failure reaches a
fully installed safe route.

## Supported mechanisms

The scope is one connected Family A route system:

- PX4 internal route;
- Legacy Offboard;
- Dynamic External Mode;
- Mode Executor;
- internal Hold, RTL, Land, and Recovery routes.

The repository contains only model definitions, observation adapters,
collectors, three contract Oracles, evidence admission, controlled generation
strategies, safety and cleanup rules, attempt accounting, schemas, tests, and a
locked validation/reference toolchain needed for that system. The formal
execution environment is supplied and registered separately for each future
experiment.

## Claim boundary

Static validation and unit tests establish internal consistency of the
implementation. They do not establish flight behavior, defect prevalence,
search effectiveness, transition pass rate, or generalization beyond the
supported mechanisms. Any empirical claim requires a new preregistered plan
that identifies the actual target environment and newly collected admissible
evidence from that environment.
