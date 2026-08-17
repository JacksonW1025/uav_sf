# Post-hoc Finding and Consequence Triage v1

## Scope and decision

This read-only analysis separates three obligations in the frozen Thor
Motivation evidence: the concentrated attitude-installation signature,
airborne freshness exposure, and Dynamic External Mode timeouts. It is part of
paper Section 6 and informs RQ4/RQ5. It changes no Stage A1 result, denominator,
threshold, ledger, trace, or evaluation.

The triage makes three decisions:

1. attitude installation is the primary source-level finding target, but its
   root cause remains unresolved until high-rate reproduction;
2. the first Stage A2 causal workload uses time-varying position-only movement
   with `SETPOINT_STALL_HEALTHY`;
3. seven common Dynamic requester-readiness timeouts block matched A2 until a
   qualified readiness contract removes the loss mode.

## Attitude installation

All 11 frozen installation violations occur in Legacy Offboard attitude cells:
four normal Land attempts and seven setpoint-stall attempts. Nine traces became
airborne and two did not, so failure to take off does not explain the
concentration.

The complete installation appears later in every trace. Observed latency from
the public transition request to actuator write is 401.749--785.004 ms, with a
median of 583.148 ms, against the frozen 300 ms research-contract bound.
Activation itself appears after only 13.459--28.866 ms. The main delay precedes
the first observed attitude command consumption, which appears after
313.790--728.991 ms; controller, allocator, and writer evidence then appears
within the same or following observation record.

All 11 ULogs use observation profile 1 with a dominant expected period of
100,000 us. Subtracting one full 100 ms observation period and each trace's
registered clock uncertainty gives conservative latency lower bounds of
300.578--683.506 ms. Under this interval model, all 11 still exceed the frozen
300 ms bound, although the minimum case is close enough that the 125 Hz
qualification remains necessary.

This localizes the signature to the activation-to-command-consumption segment;
it does not yet identify why the attitude input first becomes consumable late.
The retained evidence cannot distinguish an attitude fixture condition, PX4
input-validity behavior, or another source-level mechanism with sufficient
confidence. The classification is therefore
`UNRESOLVED_PENDING_HIGH_RATE_REPRODUCTION`, not a PX4 bug and not a public
specification violation.

## Freshness exposure

There are 41 calculable freshness-exposure windows in airborne traces. They
separate into four roles:

| Role | Windows | Maximum-age range | Median maximum displacement |
| --- | ---: | ---: | ---: |
| Injected update starvation | 8 | 5.008--5.064 s | 2.800 m |
| Injected retained attitude/rate command | 9 | 4.975--5.064 s | 0.066 m |
| Injected process exit | 16 | 1.008--1.343 s | 0.765 m |
| Incidental threshold crossing | 8 | 0.204--0.352 s | 0.936 m |

The eight update-starvation windows are exactly the airborne Legacy Offboard
trajectory-stall attempts. Every one shows 2.704851--2.845607 m maximum
displacement, dominated by vertical motion, before target-authority revocation.
The result demonstrates a repeatable SITL physical response to withholding
trajectory updates while proof-of-life continues. Because the position
reference itself is constant, it still cannot measure motion-relative lag or
separate old-reference error from update-presence semantics.

Attitude/body-rate stall has a smaller retained-command signature: nine
airborne windows have 0.037104--0.152084 m maximum displacement. Process-exit
and incidental crossings are not clean causal freshness tests because they
couple fallback/recovery or other transition timing with command age.

The selected A2 hypothesis is therefore:

```text
fault: SETPOINT_STALL_HEALTHY
setpoint semantics: time-varying position only
motion: constant-altitude straight translation
effect: motion-relative tracking lag and recovery
```

Velocity and acceleration remain unset in the first A2 profile. This retains
the Stage A1 update-starvation mechanism while adding a changing reference,
without introducing a stale nonzero velocity command as a second causal
factor.

## Dynamic timeout triage

The primary ledger contains eight Dynamic External Mode timeouts outside the
unreachable RTL fixture family.

Seven have the same split observation:

- the C++ external-mode log records one successful
  `Got RegisterExtComponentReply`;
- the Python workload lifecycle contains only `requester_started`;
- the requester records no registration reply and therefore never obtains its
  mode ID or begins takeoff/transition actions.

The retained requester source subscribes to the one registration-reply topic
and gates every action on `_mode_id`. It has no retry/query readiness contract.
This supports classification as
`CPP_REGISTERED_REQUESTER_MISSED_READINESS`, but it does not by itself prove an
exact DDS root cause.

`fault-dynamic-registration-capacity-006` is different: it records ten Python
registration replies, takeoff, and a transition request before timeout. It is
classified separately as `DISTINCT_POST_REGISTRATION_TIMEOUT` and is not used
to justify the common readiness fix.

## Stage A2 consequences

Before formal A2, qualification must establish:

- a durable or repeatable requester readiness contract under four-slot load;
- sustained height and motion-progress admissibility;
- a selected observer profile after off/10 Hz/125 Hz probe qualification;
- successful high-rate reproduction or bounded non-reproduction of the
  attitude activation-to-consumption delay.

The attitude signature and the A2 freshness hypothesis remain distinct work
items. Stage A2 tests moving update starvation across Legacy Offboard and
Dynamic External Mode; it does not need to include attitude control or claim
that the mechanisms have a general safety ordering.

## Reproduction and boundary

`input-manifest.json` binds the upstream physical-audit artifacts, threshold
observations, every installation trace/evaluation/route-observation input,
each timeout log, the primary ledger, the requester source, and the analysis
plan. The generated files reproduce without modifying frozen inputs:

```sh
python3 -m scripts.analysis.finding_consequence_triage \
  --root . \
  --analysis-plan experiments/posthoc_finding_consequence_triage_v1/analysis-plan.json \
  --output-root /tmp/posthoc-finding-consequence-triage-v1
```

The reported signatures are not independent defect counts, real-flight risk
estimates, or general PX4 failure rates. Unresolved attribution remains
explicit and is a qualification input rather than a positive finding claim.
