# Future experiment plan

Every flight experiment starts with a new plan conforming to
`data/schemas/experiment_plan.schema.json`. The plan must be committed before
execution and must identify:

- a unique plan and run identity;
- exactly one controlled generation strategy and its seed where applicable;
- source and target routes;
- expected successor and safety fallback behavior;
- whether target activation, registration rejection, activation rejection,
  fault observation, completion, and fallback installation are independently
  expected;
- revocation, installation, continuity, freshness, and progression bounds;
- required evidence event kinds;
- safety limits and terminal cleanup requirements;
- immutable repository and upstream source identities;
- the actual execution host, collector host, target kind, architecture,
  operating system, PX4 binary digest, and complete environment-manifest
  digest.

The template in `config/experiment.template.json` contains placeholders and is
not an authorization to fly. Replace every placeholder, review the resulting
plan, and record it before launching any runtime component.

The repository checkout host and its validation/reference image do not supply
the execution-environment identity. That identity must describe the system
that actually runs the experiment. Collection must begin with exactly one
`environment_attested` event whose environment object equals the registered
plan object.

The execution order is preflight, accounting registration, safety-supervisor
readiness, collector readiness, environment attestation, launch, collection
close, evaluation, cleanup, and accounting close. Any preflight or evidence
failure is recorded honestly and cannot be promoted to an empirical result.
