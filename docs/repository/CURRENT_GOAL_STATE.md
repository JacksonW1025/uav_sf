# Current Goal state

- Goal phase: Phase B, P5 recovery and stabilization
- Current gate: P5 Differential Gate, initial five-pair matrix incomplete
- Current campaign: `campaign_seeded_v5` — `INITIAL_MATRIX_IN_PROGRESS`; v3 and
  v4 are preserved and closed
- Repository checkpoint commit: `fef4b31c3b6a0ec220b98b4e7d8e1efc83e87677`
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
  excluded attempts preserved; T2 straight also has all five repeats; T4 turn
  now has `p5_t4_turn_pair_r1-r5`, `p5_t5_hover_pair_r1-r5`, and
  `p5_t6_straight_pair_r1-r4` complete, for 24 complete pairs and 48 accepted sides
- Partial/invalid paired cells: v5 `p5_t6_straight_pair_r5` is partial; its
  Dynamic attempt 1 is valid, while Legacy attempt 1 is preserved as an
  environment failure after runner return 1 and an INVALID 440.8 ms-residual
  clock bridge; all excluded attempts remain preserved, as does v4 history
  `p5_t1_hover_pair_r1` (Offboard valid; Dynamic
  attempts 1 and 2 are measurement-unknown with 18 and 17 retained clock
  samples); no v4 pair is accepted
- Pending paired cells: 10 untouched pairs beginning with
  `p5_t7_turn_pair_r1`, plus the missing Legacy side of T6 r5; no v3 or v4
  side is reused across the observation-capture revision
- Known environment failures: three recovered v3 Dynamic T1 PX4
  abort/incomplete attempts plus v4 pilot attempt 1, which failed before PX4
  readiness because a relative artifact root was resolved inside the PX4
  subshell, plus v5 r4 Offboard attempt 1 (`timeout in TAKEOFF`, PX4 SIGABRT);
  v5 T2 r3 Offboard attempt 2 timed out in `RELEASE_OFFBOARD`; v5 T6 r5 Legacy
  attempt 1 returned 1 with an invalid clock bridge after a behaviorally
  complete run; all are preserved as environment evidence, never SUT or Oracle
  violations
- Latest batch: v5 T6 r5 Dynamic attempt 1 is revision-matched, clock-valid,
  critical-window complete, and PASS for all five Route Oracle clauses; Legacy
  attempt 1 is the environment failure described above
- Next exact action: run only the missing Legacy side of T6 r5 with attempt 2
- Last update: 2026-07-18T04:57:38-07:00
