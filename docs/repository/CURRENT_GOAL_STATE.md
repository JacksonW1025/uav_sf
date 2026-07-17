# Current Goal state

- Goal phase: Phase B, P5 recovery and stabilization
- Current gate: P5 Differential Gate, initial five-pair matrix incomplete
- Current campaign: `campaign_seeded_v5` — `INITIAL_MATRIX_IN_PROGRESS`; v3 and
  v4 are preserved and closed
- Repository checkpoint commit: `82e9868f87e7da91a40ef71c139665b1bf23270d`
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
  excluded attempts preserved; T2 straight repeat 1 is also complete
- Partial/invalid paired cells: v5 `p5_t2_straight_pair_r2` has both attempt-1
  sides excluded for degraded clock bridges and requires new attempt IDs; v4
  `p5_t1_hover_pair_r1` (Offboard valid; Dynamic
  attempts 1 and 2 are measurement-unknown with 18 and 17 retained clock
  samples); no v4 pair is accepted
- Pending paired cells: both v5 T2 r2 sides at attempt 2, then 28 untouched
  pairs; no v3 or v4
  side is reused across the observation-capture revision
- Known environment failures: three recovered v3 Dynamic T1 PX4
  abort/incomplete attempts plus v4 pilot attempt 1, which failed before PX4
  readiness because a relative artifact root was resolved inside the PX4
  subshell, plus v5 r4 Offboard attempt 1 (`timeout in TAKEOFF`, PX4 SIGABRT);
  all are preserved as environment evidence, never SUT or Oracle violations
- Next exact action: checkpoint both excluded T2 r2 attempts, then rerun both
  sides as attempt 2 in the next bounded v5 matrix batch
- Last update: 2026-07-17T14:08:49-07:00
