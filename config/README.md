# Configuration and PX4 overlays

Active configuration is intentionally small:

- `m1_anchor_step.json` and `m2_safety_envelope.json` support the minimal Family B reproduction entry.
- `px4/init.d-posix/airframes/10046_sihsim_x500_v2` is installed by `scripts/setup/install_m1_sih_x500.sh`.

Pre-V4 BATON campaign configurations are archived under `archive/pre_v4_baton/configs/config/`. Board overlays live in `boards/`; source changes live in `patches/`; installers live under `scripts/setup/` and `scripts/tracing/`. The former `configs/` and `px4_overlay/` mapping-only layers were removed.
