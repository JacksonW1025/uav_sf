# Frozen threshold rationale

All durations use the normalized analysis-monotonic clock domain after the
PX4 boot-time to ROS monotonic clock bridge. The maximum admitted clock-bridge
uncertainty is 20 ms.

| Contract | Frozen bound | Basis |
| --- | ---: | --- |
| old-route revocation | 300 ms | 100 ms RouteObservability publication period, 20 ms clock allowance, and scheduling/observation margin |
| new-route installation | 300 ms | same observation and clock budget; deliberately detects paths whose full controller-to-writer lineage arrives later |
| actuator-effect gap | 250 ms | normal qualified gaps were approximately 100–200 ms; 250 ms is fixed above that normal envelope |
| command age | 200 ms | normal qualified command ages were approximately 100–152 ms; bound retains control/publication-period margin |
| completion successor | 300 ms | public completion-to-successor contract plus observation and clock margin |
| fault fallback | 1500 ms | PX4 `COM_OF_LOSS_T=1.0 s` plus route observation, clock, and scheduling margin |

The first two bounds are not widened for the qualified attitude path that took
about 780 ms to become complete. That observation is a candidate SUT finding,
not a calibration sample. Likewise, the fallback bound is based on the public
PX4 timeout configured before the fault cells, not tuned to make a target
fault pass.

Qualification used separate run identities and directories and is excluded
from every formal numerator, denominator, target, and cap.
