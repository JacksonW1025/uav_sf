# Current Goal state

- Goal phase: Phase B, formal P5 v6 paired campaign initialized
- `campaign_seeded_v6` status: `INITIAL_MATRIX_IN_PROGRESS`; formal campaign,
  authorized by `AUTHORIZED_FOR_V6_CREATION`
- P5 Differential Gate: `FORMAL_CAMPAIGN_IN_PROGRESS`
- Frozen implementation identity: commit
  `7f736c209b2818dc0d64024ffd6045c8549f0e13`; PX4
  `4ae21a5e569d3d89c2f6366688cbacb3e93437c9`; PX4 binary
  `931320a0...8993`; observation patch `73555576...e8b7c`; Dynamic adapter
  binary `af5a02a2...ef79b`; Legacy adapter source `1448d8be...1314`
- Frozen observation identity: Route Oracle `0.4`, result schema `1.3`, trace
  schema `1.2`, scenario schema `1.1`, scenario hash `e0affa...b3db5`, retained
  contract `p5-retained-route-observation-v1` / `1.0` with hash
  `41be4c...90e4c`, and threshold profile `route-oracle-v0.3-default`
- Frozen fallback: Hold; `COM_OF_LOSS_T=1.0`, `COM_OBL_RC_ACT=5`,
  `COM_RC_IN_MODE=4`, `NAV_DLL_ACT=0`, `NAV_RCL_ACT=0`, expected fallback
  nav state `4`
- Formal matrix: 35 matched pairs / 70 sides; T1/T2/T4/T5/T6/T8 use
  `TRANSITION`, T7 uses `RETAINED_ROUTE`
- Matrix progress: 28 complete pairs, 0 partial pairs, 7 pending pairs;
  56 accepted sides, 0 excluded attempts, 22 environment failures, 0 campaign
  configuration failures
- Last completed pair: retained-route cell `p5_t7_turn_pair_r3`; both attempt
  1 sides are accepted with seed `50703`, health on/setpoint off, `COMPLETE`
  3000 ms retained windows, continuity/exclusivity PASS,
  revocation/installation/recovery `NOT_APPLICABLE`, zero fallback/route
  changes/conflicts, no disallowed gap, and null transition metrics
- Current partial pair: none
- Environment diagnosis: elevated host scheduling load (10.62/9.79/9.25) is
  present, with remote-desktop and GUI CPU load but no experiment residue,
  occupied campaign port, memory exhaustion, or workspace disk pressure;
  classification remains transient run-environment instability, not
  frozen-revision drift
- Next exact action: execute only retained-route cell `p5_t7_turn_pair_r4` as
  one bounded matched pair with seed `50704`, Legacy first and Dynamic second
- Historical campaigns: `campaign_seeded_v3` and `campaign_seeded_v4` remain
  preserved/closed; `campaign_seeded_v5` remains permanently
  `CLOSED_REVISION_CHANGE_REQUIRED` with 25/35 complete pairs, 50 accepted
  sides, one partial T7 pair, and nine untouched T7/T8 pairs
- v5 manifest preservation: SHA-256
  `8c7727986b2b0200f19e5983be8fc25177d07b9ab0e97c10740525a6e329c31f`;
  v5 records and candidate pilot sides are not reused
- Baseline focused retained-route tests: PASS, `38 passed`
- Baseline full repository validator: PASS, `125 passed`, `15/15` stages
- Current blocker: none
- Last checkpoint focused tests: PASS, `38 passed`
- Last checkpoint full repository validator: PASS, `125 passed`, `15/15`
  stages
- Last update: 2026-07-18T14:25:47-07:00
