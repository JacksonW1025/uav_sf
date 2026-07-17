# P0-D1 Registration Lifecycle

Run `p0d1_lifecycle_r2_20260717` remained disarmed and exercised two component
lifetimes. The first used normal graceful shutdown; the second exited
immediately after publishing unregister. Both unregister requests were
processed successfully by PX4.

The trace contains two successful registrations with fresh
`registration_instance_id` values, two mode-slot removals, and two
arming-check-slot removals. Both registrations intentionally had no executor
slot (`-1`), so the zero executor-removal count is explicit rather than missing
evidence. No active registration remained at the end.

Result: **PASS** for unregister processing, resource removal, fresh
re-registration, and absence of stale active registration. This experiment did
not use SIGKILL; crash behavior is reserved for P2.

Processed evidence is in `data/processed/p0d1/p0d1_lifecycle_r2_20260717/`.
