# Current Goal state

- Goal phase: Phase B, P5 recovery and stabilization
- Current gate: P5 Differential Gate, initial five-pair matrix incomplete
- Current campaign: `campaign_seeded_v5` — `INITIAL_MATRIX_IN_PROGRESS`; v3 and
  v4 are preserved and closed
- Repository checkpoint commit: `12c29b3fc0fe32fa0705cf43bff73d7bdac5f7f5`
- Campaign revision identities: PX4 `4ae21a5e...`; PX4 binary `931320a0...`;
  observation patch `73555576...`; adapter `a02fc11` / binary `af5a02a2...`;
  Route Oracle `0.3`; trace schema `1.2`; threshold profile
  `route-oracle-v0.3-default`; scenario matrix `8a39d52f...`; Hold fallback
- Completed deliverables: Oracle Validation Gate; Oracle 0.3; P5 runner,
  matched matrix, fault markers, paired analysis, strengthened clock capture,
  recovery manifest reconstruction, and bounded batch/retry controls
- Current pilots: v4 Dynamic T5 attempt 2 remains revision-matched and valid;
  v5 Dynamic T1 capture attempt 1 is valid with 21 retained clock samples, a
  complete selected critical window, and a passing P5 Oracle verdict
- Completed paired cells: v5 `p5_t1_hover_pair_r1` through
  `p5_t1_hover_pair_r5`; T1 now has all five preregistered repeats, with all
  excluded attempts preserved; T2 straight repeats 1 through 4 are complete
- Partial/invalid paired cells: none in v5; T2 r3 accepted Offboard attempt 4
  after preserving its three excluded attempts; v4 history remains preserved
  `p5_t1_hover_pair_r1` (Offboard valid; Dynamic
  attempts 1 and 2 are measurement-unknown with 18 and 17 retained clock
  samples); no v4 pair is accepted
- Pending paired cells: 26 untouched pairs beginning with
  `p5_t2_straight_pair_r5`; no v3 or v4
  side is reused across the observation-capture revision
- Known environment failures: three recovered v3 Dynamic T1 PX4
  abort/incomplete attempts plus v4 pilot attempt 1, which failed before PX4
  readiness because a relative artifact root was resolved inside the PX4
  subshell, plus v5 r4 Offboard attempt 1 (`timeout in TAKEOFF`, PX4 SIGABRT);
  v5 T2 r3 Offboard attempt 2 timed out in `RELEASE_OFFBOARD`; all are
  preserved as environment evidence, never SUT or Oracle violations
- Next exact action: checkpoint the complete T2 r4 pair, then run both missing
  sides of `p5_t2_straight_pair_r5` as the next bounded v5 matrix batch
- Last update: 2026-07-17T14:36:36-07:00
