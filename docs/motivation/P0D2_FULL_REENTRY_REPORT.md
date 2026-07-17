# P0-D2 Full External Re-entry

P0-D2 ran only after P0-D0 and P0-D1 passed. Run
`p0d2_full_reentry_r3_20260717` registered and activated the Dynamic External
Mode, completed the first flight, returned and auto-disarmed, waited five
seconds, gracefully unregistered, verified slot removal, selected Internal
Hold, rearmed, completed a second low-risk internal flight, and landed.

The analyzer found one successfully processed unregister, one mode-slot
removal, one arming-check-slot removal, no post-removal data-plane events from
the old External epochs, and no automatic External reactivation after internal
rearm.

Result: **PASS — clean re-entry**. All eight preregistered checks in
`reentry_result.json` are true.

Processed evidence is in `data/processed/p0d2/p0d2_full_reentry_r3_20260717/`.
