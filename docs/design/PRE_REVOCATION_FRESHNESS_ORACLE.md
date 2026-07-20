# Pre-Revocation Freshness Oracle

Version: `0.1`. Result schema: `1.0`.

## Purpose and boundary

This oracle evaluates the interval after an External Mode producer ceases valid
setpoint publication and before PX4 installs a fallback route. It answers
whether the last external command remains influential, for how long, whether
that behavior obeys an explicit freshness policy, and what physical consequence
and recovery are observed.

It is independent of Route Oracle 0.4. Route Oracle remains authoritative for
declared route epochs, post-revocation source removal, target installation,
writer exclusivity, and continuity. A run can legitimately have:

```text
Route Oracle PASS or NOT_APPLICABLE
and
Pre-Revocation Freshness Oracle EXPOSURE
```

because the old controller/writer may still be consistent with the external
route that PX4 has not yet revoked. This oracle does not revise any historical
Route Oracle result.

## Status semantics

- `PASS`: an explicit freshness/fallback policy applies, required evidence is
  complete, behavior meets it, and preregistered physical metrics are in range.
- `EXPOSURE`: the implementation continues to use the last command without an
  explicit enforced policy sufficient to call it a violation, or a physical
  exposure threshold is exceeded. This quantifies design risk; it is not
  automatically a bug.
- `VIOLATION`: behavior breaches an explicit source/interface/preregistered
  contract, such as consumption after a policy deadline, external-route effect
  after fallback installation, or a missed fallback/recovery deadline.
- `UNKNOWN`: required time, clock, consumption lineage, window, or environment
  evidence is incomplete. An environment failure is UNKNOWN and ineligible; it
  never contributes to the SUT denominator.
- `NOT_APPLICABLE`: the profile explicitly excludes the cell, or setpoint
  production did not cease and no stale-command window exists.

Overall precedence is `VIOLATION`, `UNKNOWN`, `EXPOSURE`, `PASS`; all clauses
not applicable yields `NOT_APPLICABLE`. An `UNKNOWN` result is never eligible
for an accepted formal run.

## Inputs and clock rules

The evaluator consumes a frozen YAML/JSON profile and one compact observation
mapping. All `timestamps_us` must be in PX4 time or mapped into PX4 time through
a `VALID` clock bridge before evaluation:

```text
fault_injection
producer_last_publish
px4_last_setpoint_receive
last_setpoint_consumption
last_external_allocator_input
last_external_writer_output
health_loss_detection
fallback_declared
fallback_installed
physical_recovery
```

The library sends setpoint timestamp zero, so the locked uCDR deserializer
assigns PX4 HRT at receive time. Producer publish time is a separate harness
marker. Controller/allocator/writer observations must carry original-setpoint
lineage; their freshly generated output timestamps are not command freshness.

Required window flags are `pre_fault_stable`, `pre_revocation_target`, and
`fallback`. `SETPOINT_ONLY_STALL` may explicitly policy-terminate without a
fallback window only when the complete bounded target window proves health
alive and the external route retained. Physical metrics are measured relative
to the stable pre-fault baseline.

## Clauses

### Producer cessation

Requires the immutable fault marker, last producer publish, and proof that the
setpoint channel stopped. Publishing beyond the frozen post-fault grace is a
violation. A process stop and callback stall use the same clause even though
only process stop also removes health replies.

### Setpoint freshness

Requires PX4 receive time, controller-use lineage, and a complete target
window. With an explicit timeout, consumption after timeout plus measurement
tolerance is a violation. With no enforced timeout, demonstrated stale use is
`EXPOSURE`. Holding the last command is never automatically a violation.

### Controller continuation

Measures the last controller use attributed to the last external setpoint. It
inherits an explicit deadline violation; otherwise demonstrated retained use
is exposure. Missing periodic use evidence is UNKNOWN even if the input topic's
last sample is known.

### Allocator / writer continuation

Measures the last allocator input and final actuator output attributed to the
origin external setpoint. A fresh torque/actuator timestamp alone is
insufficient. Continued external influence after fallback installation plus the
unchanged route grace is a violation; pre-revocation continuation without an
enforced policy is exposure.

### Fallback detection

For `TOTAL_PROCESS_STOP`, compares the first health-loss detection with the
frozen health deadline. For `SETPOINT_ONLY_STALL`, complete evidence that health
replies stayed alive and no health loss was declared is PASS for this clause;
it does not make stale command use safe.

### Fallback installation

For process death, requires declaration and a new fallback route within the
post-detection deadline. For a health-alive setpoint stall, retained external
route with no fallback is the source-predicted behavior and PASSes this clause,
while the freshness/controller clauses can remain EXPOSURE.

### Physical consequence

Compares attitude excursion, angular-rate excursion, altitude loss, horizontal
displacement, and any other frozen metrics with their preregistered exposure
thresholds. Exceeding them is `EXPOSURE`, not a route violation and not proof of
causality by itself. Attribution still requires command lineage and the frozen
motion context. The adjudicated `physical_metrics` window is exactly fault to
automatic fallback installation for process death, or fault to the bounded
target-window end for a health-alive stall. Recovery and explicit-cleanup
motion is reported separately as `recovery_physical_metrics`; the diagnostic
`full_post_fault_physical_metrics` must not be used to reclassify the bounded
pre-revocation clause.

### Recovery

After fallback installation, requires the frozen physical recovery condition
within its deadline. It is not applicable to a policy-terminated health-alive
window in which fallback is not expected.

## Derived output

The evaluator emits all required fault-to-event durations, maximum observed
setpoint age, and recovery duration. Negative durations remain visible and are
not silently clamped; upstream acceptance validation must reject impossible
event sequences.

The executable is
`scripts/oracles/pre_revocation_freshness_oracle.py`; the result schema is
`data/schemas/pre_revocation_freshness_result.schema.json`.
