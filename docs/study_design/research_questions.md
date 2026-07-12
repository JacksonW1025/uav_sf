# Research Questions

The canonical wording and evidence boundaries are in `docs/narrative/CURRENT_NARRATIVE.md`.

## RQ1 — Contract and compliance

What admission, handover, residual-state, and fallback obligations govern actuator-authority transfer, and where does deployed PX4 behavior comply or violate them?

## RQ2 — Automatic detection

Can traceable static and runtime checkers detect silent violations such as stale configuration, incomplete admission replies, continued classical execution, and multiple actuator writers?

## RQ3 — Risk and causal diagnosis

Which contract violations add physical risk relative to holding the original controller, and which mechanism/controller/trigger/history differential explains the result?

## RQ4 — Test validity

How does wall-clock versus sim-time/lockstep orchestration affect state alignment and repeatability? The preregistered anchor result is `confirmed`; older boundary-shape claims remain `legacy_unverified`.

## Optional RQ5 — Search efficiency

After harness hardening, can stateful search localize confirmed violations more efficiently than controlled baselines? This question must not reuse legacy boundary claims as confirmed evidence.
