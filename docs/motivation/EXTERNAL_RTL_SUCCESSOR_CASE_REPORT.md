# External RTL successor motivation case report

Date: 2026-07-19

Study: `external_rtl_successor_issue_162`

Final disposition: `HISTORICAL_DEFECT_REPRODUCED`

## Executive conclusion

The bounded study reproduced one historical defect. On the reported affected
stack, a legal RTL request selected and executed the registered External RTL
mode, but PX4 kept Autopilot executor `0` in charge instead of the mode's
registered executor `1`. The External RTL reached its home-above target and
published successful completion. That completion did not reach the executor's
active scheduled-mode receiver, so the executor did not request Land. No Land
selection or Land route epoch followed, and the vehicle remained armed,
airborne, and in External RTL for the complete five-second post-completion
window.

Three of three preregistered fully instrumented attempts reproduced this chain.
The separate, preregistered instrumentation-reduced confirmation reproduced it
once in one attempt. The result is therefore
`HISTORICAL_DEFECT_REPRODUCED`, with one confirmed issue, three accepted formal
reproductions, and one accepted reduced-observation confirmation.

The current locked library does not provide this successor chain. It rejects
the composition during construction with exit code `42`, before registration
or flight. Its classification is `NOT_REPRODUCED_ON_CURRENT` with disposition
`UNSUPPORTED_COMBINATION_REJECTED`, not a functional successor PASS.

## 1. Issue #162 provenance

The primary case is
[Auterion/px4-ros2-interface-lib Issue #162](https://github.com/Auterion/px4-ros2-interface-lib/issues/162),
“Mode Executor with RTL Internal Mode Replacement,” opened 2025-10-22. The
closely matching PX4 report is
[PX4/PX4-Autopilot Issue #25707](https://github.com/PX4/PX4-Autopilot/issues/25707).
Both describe the ownership split produced when an internal RTL intention is
mapped to an external replacement while executor ownership remains associated
with the unreplaced intention. The authoritative local review and target
selection are in `EXTERNAL_RTL_SUCCESSOR_ISSUE_INVENTORY.md`.

The preregistered public trigger was a normal RTL mode request. Direct state
mutation, a seeded lifecycle fault, or a PX4 behavior patch that creates the
target problem was forbidden and was not used.

## 2. Normal successor baseline: 3/3

The legal non-replacement baseline isolates the lifecycle mechanism from RTL
replacement. Its sequence is:

```text
Takeoff
→ executor-owned non-replacement External Mode
→ public successful completion
→ owning executor requests Land
→ Land selected and installed
→ Disarm
```

Accepted seeds `16201`, `16202`, and `16204` pass Route Oracle 0.4 and all five
Successor Progression Oracle 0.1 clauses. In every accepted run, registered
executor `1` is in charge of owned mode `23`; completion is generated and
delivered to that executor; component `1001` requests Land using
`VEHICLE_CMD_SET_NAV_STATE (100001), param1=18`; Commander selects Land; and a
distinct Land route epoch `5` follows source epoch `4`.

Completion-to-request latency is `2.480–3.316 ms`, request-to-selection latency
is `15.405–30.085 ms`, and selection-to-Disarm time is `6.347–6.403 s`. Route
Oracle records complete producer/controller/writer coverage, zero
post-revocation consumption or writes, and at most a `12 ms` unowned window.
This establishes that the harness, public completion path, executor Land
request, route-transition observation, and terminal evaluator work when the
ownership composition is legal.

## 3. Current-version guard rejection

The current replay locks px4-ros2-interface-lib
`c3e410f035806e8c56246708432ded09c976434b`. It observes the exact guard added
by `dce6c1f2e4a29e947fd32a84c4981773f1962c03`:

```text
A mode executor cannot be used in combination with a mode that replaces an internal mode. See https://github.com/PX4/PX4-Autopilot/issues/25707
```

The single allowed attempt, `successor_current_c3e410f_r1`, has:

- exit code `42`;
- exact guard-exception match;
- `registration_attempted=false`;
- `flight_started=false`;
- classification `NOT_REPRODUCED_ON_CURRENT`;
- disposition `UNSUPPORTED_COMBINATION_REJECTED`.

The replay source SHA-256 is `a23b1ffa...59fcc`, executable SHA-256 is
`272eae42...d6297`, library binary SHA-256 is `dddfa069...80e6`, and PX4
binary SHA-256 is `931320a0...8993`. The result proves prevention, not current
functional support for External RTL completion followed by Land.

## 4. Historical affected revision identity

The isolated affected stack exactly matches the preregistration:

| component | locked identity |
|---|---|
| px4-ros2-interface-lib | `release/1.16`, tag/describe `1.5.2`, commit `a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684` |
| PX4 | `v1.16.0`, commit `6ea3539157ca358c70a515878b77077af7d4611d` |
| px4_msgs | `392e831c1f659429ca83902e66820d7094591410` |
| ROS / OS | ROS 2 Jazzy in rootless Ubuntu 24.04.4 Noble namespace |
| simulator | Gazebo SITL |

The historical library binary SHA-256 is `bfb9d81a...5302c`; the harness
binary is `b7a23fe3...327b66`; and the historical PX4 TRANSITION-profile binary
is `e6b2f64e...0027`. The reviewed PX4 observation-only diff is
`009c4d52...002a`.

All builds, installs, processes, ports, and run namespaces are independent of
the current `c3e410f` workspace, locked current PX4 worktree, protected P5 v6
campaign, baseline artifacts, and current replay artifacts.

## 5. Shared harness and compatibility adaptation

The current and historical replay use the same core source and lifecycle:
register External RTL as the internal RTL replacement and executor-owned mode,
take off through public interfaces, request RTL publicly, fly to home-above NED
`[0, 0, -5] m`, remain within `0.5 m` position and `0.5 m/s` speed for
`1000 ms`, call `completed(Success)`, and expect the owner to request Land and
wait for Disarm.

The only historical API adaptation translates constructor spelling:

- mode settings use `Settings(component_name, false, ModeBase::kModeIDRtl)`;
- executor construction uses `ModeExecutorBase(node, Settings{}, owned_mode)`.

The adapted source SHA-256 is `f25c8847...2e6b`. The change preserves
armed-only activation, internal RTL replacement, ownership, public completion,
Land successor, and terminal Disarm semantics. It neither bypasses registration
nor fabricates an ownership mismatch.

## 6. Expected lifecycle

The preregistered expected chain is:

```text
legal RTL request
→ External RTL mode 23 registered and selected
→ registered executor 1 in charge
→ home-above completion condition stable for 1000 ms
→ successful completion generated and delivered to executor 1
→ executor component 1001 requests Land within 1000 ms
→ Commander selects Land within 1000 ms
→ distinct Land route epoch installs within 300 ms
→ external route releases
→ Land
→ Disarm
```

The baseline establishes this as an observable and executable lifecycle rather
than an assumed sequence.

## 7. Observed historical lifecycle

Every accepted affected run observes the following instead:

```text
mode 23 and executor 1 register
→ legal RTL request selects External RTL mode 23
→ External RTL route produces and reaches the home-above target
→ executor_in_charge remains Autopilot 0
→ completion condition is reached and successful completion is published
→ executor 1 has no active completion receiver for that mode
→ no Land request
→ no Land selection or Land route epoch
→ mode 23 remains active and its route remains installed
→ vehicle remains armed and airborne for at least 5000 ms
→ no Disarm
```

No accepted attempt has an infrastructure abort, early executor exit, trigger
failure, incomplete target window, identity mismatch, or protected-state drift.

## 8. Executor ownership evidence

Registration assigns External RTL mode ID `23` and its owner executor ID `1`.
During the active External RTL interval, `VehicleStatus.executor_in_charge` is
consistently `0`, the Autopilot executor. The lifecycle monitor independently
records active mode `23`, owned mode `23`, registered owner `1`, and observed
executor `0` in the same clock-valid window.

This is a direct `EXECUTOR_NOT_IN_CHARGE` violation. It is not inferred from the
later hover and is not created by an illegal registration shortcut.

## 9. Completion evidence

The harness reaches the preregistered position, speed, and one-second stability
condition, then calls `ModeBase::completed(Result::Success)`. The public
`ModeCompleted` event for mode `23` is observed. However, executor `1` was never
put in charge, so its scheduled-mode state is not active for this replacement
selection and no matching completion callback is received.

The classification is `COMPLETION_NOT_DELIVERED`: generation and public
publication succeed, but delivery to the lifecycle owner required to advance
the executor state machine does not.

## 10. Land request, selection, and installation evidence

The complete target windows contain no Land command from component `1001` or
any other valid executor requester. Consequently there is no Land navigation
selection, no External→Land declared transition, and no distinct Land route
epoch. Each accepted attempt records an External source route and full
producer/controller/allocator/writer activity, while `land_route_epoch=false`.

The resulting violations are `EXPECTED_SUCCESSOR_NOT_REQUESTED`,
`EXPECTED_SUCCESSOR_NOT_INSTALLED`, and `EXTERNAL_ROUTE_NOT_RELEASED`. The
absence is proved over the full preregistered deadline and hover window; it is
not an artifact of stopping observation at completion.

## 11. Route Oracle 0.4 result

Route Oracle 0.4 reports `NOT_APPLICABLE` with interpretation
`NOT_APPLICABLE_NO_SUCCESSOR_TRANSITION` for all accepted affected runs. This is
the correct result: there is no External→Land transition whose installation,
continuity, exclusivity, revocation, or recovery clauses could be evaluated.

`NOT_APPLICABLE` is not a route PASS and does not weaken the defect finding.
The route trace still proves that the External RTL source route exists and
continues through producer, controller consumption, allocator input, and final
writer layers; it also proves the complete absence of a Land epoch.

## 12. Successor Progression Oracle 0.1 result

Successor Oracle 0.1 reports `VIOLATION` on all five clauses in every accepted
affected run:

| clause | result | decisive evidence |
|---|---|---|
| ownership | `VIOLATION` | active/owned mode `23`, expected executor `1`, observed executor `0` |
| completion | `VIOLATION` | successful completion generated and public, but not delivered to owner |
| successor request | `VIOLATION` | no Land request in complete deadline window |
| successor installation | `VIOLATION` | no Land selection or Land route epoch |
| mission progression | `VIOLATION` | no deactivation, Land, or Disarm; armed airborne hover persists |

The complete category set includes `EXECUTOR_NOT_IN_CHARGE`,
`COMPLETION_NOT_DELIVERED`, `EXPECTED_SUCCESSOR_NOT_REQUESTED`,
`EXPECTED_SUCCESSOR_NOT_INSTALLED`, `LIFECYCLE_DEAD_END`,
`UNEXPECTED_HOVER_AFTER_COMPLETION`, `LAND_NOT_REACHED`, and
`DISARM_NOT_REACHED`.

## 13. Mission consequence

The External RTL behavior itself reaches the intended home-above target. The
mission nonetheless stops progressing because the lifecycle owner never
receives completion and therefore never requests Land. At the end of each
complete post-completion window the vehicle is still armed, airborne, and in
mode `23`. It neither lands nor disarms.

This is an armed-airborne lifecycle dead end, not an inability of the custom
mode to navigate to its target.

## 14. Reproduction attempts and rate

| attempt class | count | accepted result |
|---|---:|---|
| fully instrumented formal affected runs | `3/3` | three matching `HISTORICAL_DEFECT_REPRODUCED` |
| instrumentation-reduced confirmation | `1/1` | matching `HISTORICAL_DEFECT_REPRODUCED` |
| historical environment retries | `1` | excluded `ENVIRONMENT_FAILURE` before registration |
| historical observability rejections | `4` | excluded; not promoted despite the same recorded defect pattern |

The accepted fully instrumented runs are seeds `16214`, `16216`, and `16217`.
Their clock bridges are VALID, cover External activation through completion plus
five seconds, and have maximum residuals of `80.794 ms`, `41.587 ms`, and
`46.819 ms`. The reduced run is seed `16218`; its BASELINE observation cadence
is `100 ms` instead of `8 ms` (12.5× less frequent), its bridge is VALID with
`6.299 ms` maximum residual, and it repeats the same five-clause violation.

The one environment retry failed before registration because the newly built
historical instance lacked its generated `rootfs/0/etc` link. The runner fixed
and validates that instance-local link without changing the SUT. Four complete
flights were conservatively rejected for DEGRADED or target-window-insufficient
clock bridges; none contributes to the reproduction numerator or denominator.

## 15. Current-versus-historical differential

| dimension | current locked library `c3e410f` | historical affected library `a5b9f3c` |
|---|---|---|
| composition construction | explicitly rejected | allowed |
| registration | not attempted | mode `23`, executor `1` registered |
| flight | not started | External RTL selected and executed |
| owner in charge | not applicable | Autopilot `0`, not registered owner `1` |
| completion | not applicable | reached, generated, public, not delivered to owner |
| Land successor | not applicable | request, selection, and route all absent |
| terminal outcome | no runtime chain | armed airborne hover / lifecycle dead end |
| classification | `NOT_REPRODUCED_ON_CURRENT` | `HISTORICAL_DEFECT_REPRODUCED` |

The current constructor guard prevents the historical failure mode by banning
the composition. It does not demonstrate that the intended composable
replacement→completion→Land chain works on current software.

## 16. Candidate root cause

The strongest source-and-runtime explanation is a split between executor
selection and replacement-mode selection in historical PX4:

1. `ModeManagement::onUserIntendedNavStateChange()` determines the executor
   from the user-intended nav state. An RTL intention is an internal, unowned
   mode, so a user request assigns Autopilot executor `0`.
2. `ModeManagement::getNavStateReplacementIfValid()` separately maps internal
   RTL to the responsive external mode `23`; it does not update the executor.
3. Commander publishes replaced `nav_state=23` beside the unchanged
   `executor_in_charge=0`.
4. `ModeExecutorBase::vehicleStatusUpdated()` activates executor `1` only when
   its ID equals `executor_in_charge`. It therefore does not enter the scheduled
   owned-mode lifecycle.
5. The mode can still publish `ModeCompleted`, but the executor's scheduled-mode
   receiver only advances an active matching schedule. Its completion callback
   does not run, so `land()` is never called.

The identity-locked runtime evidence matches every step of this candidate
mechanism. The study does not claim a minimal source patch or prove all possible
failsafe semantics. The later library guard at `dce6c1f` is consistent with an
upstream decision to prevent, rather than implement, this composition.

## 17. Motivation significance

Mode and route behavior alone are insufficient evidence of mission progress.
Here the External RTL mode is registered, selected, physically successful, and
continues to command a fully observed control route. A mode-state-only check can
therefore appear healthy while the mission has lost its lifecycle owner and can
no longer reach Land or Disarm.

The study demonstrates the exact motivation claim:

> Mode/External RTL behavior itself can succeed, but incorrect executor
> ownership blocks the Land successor after completion. Mode-state-only checks
> miss the mission-chain deadlock; a successor/ownership Oracle locates the
> missing step.

Route Oracle remains necessary to prove what route exists, but Successor
Progression Oracle is necessary to explain why no next route is created. The
two Oracles answer different questions and must not be collapsed into a
route-only PASS.

## 18. Limitations and evidence boundary

- The result is SITL evidence on one reported affected library revision, PX4
  `v1.16.0`, ROS 2 Jazzy, Gazebo, and the preregistered multicopter scenario; it
  is not a hardware-in-the-loop or flight-test claim.
- The study confirms one issue. Repeats estimate reproducibility for this
  harness, not population-level failure probability.
- Four complete historical flights were excluded by unchanged observability
  rules. Their apparent lifecycle pattern is reported only as preserved context,
  never counted as PASS or VIOLATION.
- Route Oracle is deliberately `NOT_APPLICABLE` after the absent Land request;
  it cannot assess a transition that never exists. The Successor Oracle and
  complete post-completion observation establish that absence.
- Current software prevents the composition. This study does not claim current
  functional support, nor does it test a hypothetical removal of the guard.
- The candidate root cause is supported by locked source and runtime evidence,
  but no causal source mutation was introduced because the preregistration
  forbids behavior patches that create or remove the target problem.

## Evidence and integrity summary

Primary records are the preregistration, `baseline_attempt_ledger.yaml`,
`current_replay_attempt_ledger.yaml`, and processed attempt directories under
`data/processed/motivation/successor/`. Raw ULog, lifecycle, executor, monitor,
and PX4 logs remain in ignored per-attempt run directories and are referenced by
SHA-256 from the ledger.

The accepted reduced confirmation additionally proves the finding survives a
12.5× reduction in observation publication cadence with unchanged SUT source
commit, observation diff, lifecycle contract, Oracle rules, and evidence
thresholds. Protected P5 v6 Gate and manifest hashes remain respectively
`9542eb7c...32bc` and `02d857f5...2518` in every accepted classifier result.
