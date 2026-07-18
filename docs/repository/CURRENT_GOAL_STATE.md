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
- Matrix progress: 7 complete pairs, 1 partial pair, 27 pending pairs;
  15 accepted sides, 0 excluded attempts, 6 environment failures, 0 campaign
  configuration failures
- Last completed pair: `p5_t2_straight_pair_r2`
- Current partial pair: `p5_t2_straight_pair_r3`; Legacy attempt 1 is accepted;
  Dynamic attempt 1 is preserved as `ENVIRONMENT_FAILURE` after its otherwise
  complete return-0 run produced a `DEGRADED` clock (143.421 ms residual)
- Next exact action: retry only the Dynamic External Mode side of
  `p5_t2_straight_pair_r3` as attempt 2 with matched seed `50203`
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
- Last update: 2026-07-18T11:55:20-07:00
