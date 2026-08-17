# Phase III runtime and observer qualification

Status: **PASS**. These are non-formal qualification attempts and do not enter a paper experiment denominator.

All three matched observer tasks were accepted, satisfied the sustained physical-takeoff predicate, and exceeded the preregistered stable real-time-factor floor. The observer-off ULog correctly contains no Route observation topic, so it cannot be used to evaluate the Route Oracles.

The selected A2 profile is **transition**. It retained 7751 Route observations with no sequence gap or dropout. Compared with the baseline profile, its ULog grew by 443055 bytes (9.01%); this remains below the frozen bound.

The repaired Dynamic readiness path was accepted in both Dynamic qualification attempts and loaded the explicit registration handoff. The Legacy Offboard control attempt was also accepted. This sample demonstrates the handshake under the qualification batch; it is not a population-level reliability estimate.

## Claim boundary

The result qualifies one Thor SITL runtime and one observer profile for the separately preregistered A2 study. It does not alter Stage A1, prove absence of probe effects in every workload, or establish real-flight behavior.
