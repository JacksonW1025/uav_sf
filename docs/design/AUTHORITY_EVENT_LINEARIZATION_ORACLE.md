# Authority Event Linearization Oracle

Version: 0.2

The Oracle evaluates two public authority/lifecycle events issued within a
bounded local PX4/Gazebo SITL window. It asks whether the observed final route
is equivalent to at least one legal serial order while preserving unique
ownership, explainable executor state, final revocation lineage, writer
exclusivity/continuity, and safe Land/Disarm cleanup.

## Inputs and clock rule

The Oracle consumes the C1 monitor result and JSONL event stream, a collected
Route trace, and a clock bridge. Both pair events must be individually visible.
Cross-domain window selection is allowed only when the bridge is `VALID` and
the complete pair window lies within its valid interval. Missing input,
window, route, writer, or cleanup evidence produces `UNKNOWN`, never PASS or
VIOLATION.

The effective cross-domain control window excludes one measured clock-bridge
uncertainty bound at both ends. The route-context window may look back 500 ms
to admit a registered precondition route, but it ends at the same conservative
pre-cleanup boundary. Commands and control events issued after
`linearization_window_closed`, including RTL/Land cleanup, are never evaluated
as part of the event pair.

## Registered timing orders

- `A_FIRST`: event B follows event A by at least 250 ms.
- `NEAR_SIMULTANEOUS`: absolute separation is at most 100 ms.
- `B_FIRST`: event A follows event B by at least 250 ms.

The gap deliberately separates clear deterministic interleavings from the
near-simultaneous slot. It is not a timing sweep.

## Legal final-route model

`C1-A` permits Hold after activation→Hold, External after Hold→activation, and
either for the near slot. `C1-B` permits Hold. `C1-C` permits RTL. `C1-D`
permits External for fallback→re-entry, RTL for re-entry→fallback, and either
near the boundary. `C1-E` begins from installed fallback and permits RTL after
release/failsafe-clear interleavings.

The final state is captured before cleanup. Later RTL/Land/Disarm commands are
outside the linearization window.

## Clauses

1. `input_observability`: both registered inputs occur exactly once.
2. `relative_timing`: actual monotonic order matches the slot.
3. `linearizable_final_route`: the pre-cleanup route matches a legal serial
   result.
4. `owner_uniqueness`: final authority is singular and the executor remains
   the explainable Autopilot executor (`0`), because the C1 subject registers
   an External Mode but no Mode Executor.
5. `final_revocation_lineage`: no control-chain event after the final route
   transition carries an older route epoch.
6. `writer_exclusivity_and_continuity`: no timestamp has competing final
   writers and the output gap is at most 24 ms.
7. `cleanup`: the vehicle reaches Land/Disarm.

Overall status is `VIOLATION` only with complete evidence and a failed
applicable clause. Incomplete evidence is `UNKNOWN`; an unregistered pair or
timing order is `NOT_APPLICABLE`. This Oracle establishes deterministic state
grammar for later bounded state-space exploration; it does not claim search
effectiveness.
