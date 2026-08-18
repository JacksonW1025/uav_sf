# Active schema boundary

Only two partial, V8-relevant contracts remain active after repository
consolidation:

- `route_event.schema.json` is the current normalized-event skeleton. It does
  not prove that every identity field is independently observed.
- `attempt_event.schema.json` retains append-only accounting semantics.

The V8 plan, campaign, episode, semantic-state, combined-admissibility, result,
and finding-confirmation schemas do not exist yet. Their absence is an honest
implementation state, not permission to reuse an earlier schema.
