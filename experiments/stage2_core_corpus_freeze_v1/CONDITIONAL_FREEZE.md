# Stage 2 Conditional Corpus Freeze v1

## What this document is

A decision record. It fixes the parts of the Stage 2 corpus selection that do
not depend on new implementation, and states exactly what must be true before
the selection is signed.

It freezes no denominator, authorizes no flight, and changes no closed study.

## Why the freeze is conditional

The plan expects Stage 2 to freeze a minimal representative corpus. Freezing
one today would be premature for a mechanical reason: the generator cannot
select an action at all.

[live_strategy_backend.py](../../scripts/runtime/live_strategy_backend.py)
takes a single action backend from the matrix cell, evaluates a constant
`STATE`, and chooses only among five timing offsets. The decision space of a
launch is therefore one preconfigured action by five timing bins. That space is
exhausted in five launches, which is consistent with the one completed
comparison, where bounded random and the state-aware prototype tied on coverage
and every strategy reached the same signature on its first launch.

A corpus frozen over that decision space would guarantee a null generation
result by construction rather than by nature. The selection below is therefore
recorded now and signed after the actions become runtime-selectable and
separately qualified.

## Decision 1 — the proposed core action set is seven actions

Six already exist as fixtures with retained evidence; one is new.

| Action | Phase | Targets | Status |
| --- | --- | --- | --- |
| `stop_owned_setpoint_stream` | execution | `command_stale` | live-wired |
| `terminate_owning_producer` | fallback | `fallback_installed` | live-wired |
| `adjacent_land_request` | replacement | `successor_installed` | fixture, port required |
| `re_enter_route_after_successor` | re-entry | `target_installed`, `source_revoked` | fixture, port required for one mechanism |
| `withhold_health_reply` | activation | `activation_rejected` | fixture, dynamic only |
| `exhaust_registration_capacity` | registration | `registration_rejected` | fixture, dynamic only |
| `restart_producer_after_loss` | fallback | `target_installed` | new |

The set stops here. The plan asks for a minimal corpus, and the obvious reason
to grow it — that every freshness finding might be an artefact of one injection
fixture — does not hold: the retained process-exit cells reach `command_stale`
through a different mechanism than the owned stall. Communication delay,
operator takeover, concurrent producers and induced failsafe stay outside the
core corpus as named gaps.

`restart_producer_after_loss` is the only addition. It is the sole proposed
action whose legality depends on the outcome of an earlier action: a producer
can be restarted only after its loss has already driven a safe route into
place. Without at least one such action, a comparison between feedback-guided
and feedback-free generation has very little to measure.

## Decision 2 — two mechanisms, with an orthogonal grammar where the system allows

The compared mechanisms are `legacy_offboard` and `dynamic_external_mode`.
`mode_executor` stays in the Motivation evidence and leaves the main comparison.

Action availability separates two different reasons for a limit:

| Action | legacy offboard | dynamic external mode | Nature of the limit |
| --- | --- | --- | --- |
| `stop_owned_setpoint_stream` | implemented | implemented | — |
| `terminate_owning_producer` | implemented | implemented | — |
| `adjacent_land_request` | port required | port required | incidental: the request is a public Land command, implemented today only for the mode executor; the port is an anchoring change |
| `re_enter_route_after_successor` | implemented | port required | incidental: the dynamic requester has no repeat-cycle loop |
| `withhold_health_reply` | not applicable | implemented | inherent: legacy offboard has no health-reply protocol |
| `exhaust_registration_capacity` | not applicable | implemented | inherent: legacy offboard has no registration protocol |
| `restart_producer_after_loss` | new | new | — |

The two inherent limits are properties of the system under test and are
recorded as such. The two incidental limits are harness gaps and must be closed
before signing, so that the action grammar is orthogonal wherever the system
permits it. After closing them, nothing in the core corpus needs the mode
executor, which is why it leaves the comparison.

## Decision 3 — baselines are deferred, with two invariants kept

The missing comparable baselines — systematic enumeration and state-conditioned
but feedback-free generation — are not scheduled now.

Two properties are kept so deferring costs nothing later:

- timing stays five discrete bins rather than a continuous interval; and
- the core corpus stays at about seven actions.

With seven actions and five bins, the single-action layer is 35 points, which
systematic enumeration can exhaust in roughly 35 launches. The length-two
sequence layer is about 1225 points, which it cannot exhaust under any budget
we would preregister. Measured throughput at the qualified four-way concurrency
is 2.8 to 3.6 closed launches per minute, so that second layer is on the order
of seven hours of continuous execution. Keeping both properties preserves the
gap between an enumerable layer and a non-enumerable one, which is where a
generation comparison has something to measure.

## Frozen workload

- profile: the `straight_line` moving workload whose physical-validity contract
  Stage A2 established;
- setpoint kind: trajectory only. Attitude and body-rate variants stay out of
  the main comparison because they produced the non-airborne stratum in the
  Stage A1 physical audit, and mixing a physical-validity risk into a
  generation comparison would confound it. They remain a separate discovery
  question.

## Excluded, with reasons

| Excluded | Reason |
| --- | --- |
| `register_external_mode`, `request_external_activation`, `nominal_completion_release`, `mode_executor_completion` | episode scaffolding executed every time, not a selectable stimulus |
| `setpoint_kind_variation` | a workload axis, and a physical-validity risk in the main comparison |
| `route_re_entry_through_rtl` | the intermediate safe route is a parameter of the re-entry action, not a separate action; Hold is selected and RTL is what retained evidence happens to exercise |
| `communication_delay_or_reconnect`, `manual_or_gcs_takeover`, `concurrent_external_producers`, `failsafe_takeover` | no implementation and no evidence; each needs its own qualification, and induced failsafe needs a safety re-qualification |

## Conditions for signing

1. The decision interface selects an action and a timing, from the derived
   semantic state, instead of a timing alone for a preconfigured action.
2. The two incidental availability gaps are closed.
3. `restart_producer_after_loss` is implemented.
4. Every action has a non-formal qualification recording that its precondition
   gates execution, its applied schedule is recorded, and its cleanup holds.
5. The precondition replay in this directory still reports every action as
   consistent, and no action remains unvalidated.

Until all five hold, this document is a proposal with evidence attached, not a
frozen corpus.
