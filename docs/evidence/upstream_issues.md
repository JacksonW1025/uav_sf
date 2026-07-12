# Upstream Issue Ledger

| Issue | Evidence status | Local evidence | Next action |
|---|---|---|---|
| external-mode cached `config_control_setpoints` rejected after activation because the registration-time timestamp is stale | `mechanism_observed` | Round-4 causality verdict; PX4 commit audit | implement/test freshness repair and compare behavior |
| internal external-mode admission reply fields not value-initialized | `mechanism_observed` | provenance/handoff and guard-slot audits | add initialization regression test and measure admission behavior |

This is an evidence ledger, not a claim that an upstream report or patch has been accepted. Upstream URLs/status are `unknown` unless separately verified.
