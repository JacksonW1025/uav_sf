# Current research scope

The current topic is **Testing Route-Replacing Authority Transitions in PX4**.

The central question is whether a declared transfer from Route A to Route B is reflected by the complete runtime control path:

1. the old path is revoked promptly;
2. the new path is completely installed;
3. the transition window remains exclusive and continuous;
4. the safe path is completely restored after failure.

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
Repository cleanup
→ Route observability feasibility
→ Motivation Study M1–M5
→ Motivation probes
→ Fuzzer development
```

This repository currently stops at Motivation Study workspace initialization. It does not authorize a new large-scale campaign or full fuzzer implementation.
