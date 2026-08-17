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
and live safety/cleanup close, a barrier across every live attempt in the
batch, offline evidence processing and evaluation, compact retention, and
accounting close. No ULog, clock, Gate, or Oracle processing starts while
another attempt in the batch is still live. Any preflight or evidence failure
is recorded honestly and cannot be promoted to an empirical result.

The current Thor runtime can directly execute new official-sequence matrices
composed from the existing live fixture semantics: the retained constant
trajectory, attitude, body-rate, fault, rejection, adjacent-request, and
re-entry actions, plus the qualified Stage A2 position-only straight-line
workload. Stage A2 has its own completed preregistration, identities, ledgers,
physical analysis, and denominator; those artifacts do not authorize a new
study or a different generation strategy.

Bounded-random and state-aware policy selection can be preregistered and tested
offline, but their live PX4 action backend is not yet implemented. The formal
campaign validator rejects those strategy names rather than silently running
the official sequence under a different label.
