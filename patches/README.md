# PX4 patches

Tracked patches are the canonical source for PX4 modifications that cannot be expressed as a board or airframe overlay.

- `px4/m2b_state_shim.patch`: retained Family B state-channel instrumentation used by the minimal reproduction path.

Apply patches only through idempotent installer scripts. The ignored PX4 clone must not be treated as the canonical modified source. The pre-V4 unclipped RAPTOR ablation patch is archived under `archive/pre_v4_baton/configs/patches/`.
