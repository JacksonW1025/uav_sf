# P0-D0 Internal Rearm Baseline

Run `p0d0_internal_rearm_r4_20260717` passed the internal-only sequence:
takeoff, RTL, automatic disarm, 5 s wait, Internal Hold selection, rearm,
second hover, and landing. No External Mode or Executor process was started.

The measured delay from first automatic disarm to the successful second arm
was 5.200 s. Position and altitude estimates were valid at the rearm point,
the vehicle was landed, and all arm/mode command acknowledgements used by the
successful path returned accepted. The observed failsafe flags were normal
unavailable-link flags for this no-RC/no-GCS setup and did not prevent rearm.

Result: **PASS**. The locked SITL, estimator, home state, land detector, and
commander support rapid internal rearm after RTL auto-disarm. The clock bridge
was degraded for this internal-only diagnostic, so cross-domain latency is not
claimed.

Processed evidence is in `data/processed/p0d0/p0d0_internal_rearm_r4_20260717/`.
