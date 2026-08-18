# Configuration boundary

This directory contains two kinds of V8-relevant material:

- `dependencies.lock.json` fixes the upstream source identities and the
  repository-validation container base used at the current boundary.
- `method.defaults.json`, `safety_limits.*.json`, and `stage_a2_*.json` are
  retained inputs to the V8-cited Motivation and Stage A2 evidence. They are
  evidence-support configuration, not templates for a new V8 experiment.

There is intentionally no active experiment-plan template, strategy
configuration, observation-patch lock, or formal campaign configuration. New
versions may be added only at the corresponding gates in the experiment plan.
