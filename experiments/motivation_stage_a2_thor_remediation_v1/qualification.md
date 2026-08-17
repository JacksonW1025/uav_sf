# Remediation qualification

The exact remediation image was tested in a four-arm, paired-seed batch outside
the formal ledger. All arms were runtime-accepted and subsequently passed ULog
integrity, the Evidence Gate, sustained takeoff, takeoff-before-transition,
motion entry, and applicable profile coverage.

Both nominal arms evaluated `PASS`. Both healthy-stall arms produced admissible
`VIOLATION` evidence, as expected for the deliberately withheld setpoint
stream; violations are accepted evidence and are not retried away.

Qualified image: `sha256:87d4a8f9f43031cc97b6b0c156fd7a9e099a8858b2c596305ae4efe55d8f449a`.
Qualified revision: `aee070050e1dd43842df605e3b5d3b073a48904e`.
Qualification inputs are retained under
`runs/stage-a2-remediation-qualification/` and excluded from every formal
denominator.
