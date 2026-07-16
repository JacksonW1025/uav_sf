# Route profile schema

A route profile is a declarative description of an expected runtime path. Profiles support Motivation probes and replay; they are not fuzzer genomes.

## Required keys

```json
{
  "schema_version": "1.0",
  "profile_id": "descriptive-id",
  "family": "A",
  "declared_mode": "TBD",
  "registration_state": "TBD",
  "authority_source": "TBD",
  "producer_identity": [],
  "setpoint": {
    "level": "TBD",
    "topics": [],
    "maximum_age_ms": null
  },
  "modules": {
    "required_enabled": [],
    "required_bypassed": []
  },
  "allocator_input": "TBD",
  "actuator_writer": "TBD",
  "failsafe_state": "TBD",
  "fallback_target": "TBD",
  "timing": {
    "timestamp_domain": "TBD",
    "revocation_deadline_ms": null,
    "installation_deadline_ms": null,
    "maximum_overlap_ms": null,
    "maximum_gap_ms": null
  },
  "evidence": []
}
```

`TBD` and `null` mean the value has not yet been established. A profile is not executable until the observability matrix identifies collection methods for its required fields and validation confirms the profile has no unresolved timing or writer-attribution keys.

## Evidence entries

Each evidence entry should contain a signal/topic, collector version, timestamp domain, source artifact hash, and the route field it supports. Mode-state evidence alone cannot satisfy producer, module, allocator, or writer fields.
