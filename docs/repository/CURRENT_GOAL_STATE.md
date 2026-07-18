# Current Goal state

- Goal phase: Phase B, P5 revision-blocking issue
- Current gate: P5 Differential Gate — `INCONCLUSIVE`; the preregistered matrix
  is incomplete because frozen T7 transition selection cannot classify a
  conforming retained-route observation
- Current campaign: `campaign_seeded_v5` — `CLOSED_REVISION_CHANGE_REQUIRED`;
  v3 and v4 are also preserved and closed
- Repository checkpoint commit: `3930909408601c3dc2bbd6c602a8bd2113371de4`
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
  `p5_t6_straight_pair_r1-r5` complete, for 25 complete pairs and 50 accepted sides
- Partial/invalid paired cells: v5 `p5_t7_turn_pair_r1` is partial; Legacy
  attempt 1 is an environment failure after PX4 exited with required artifacts
  absent, while Dynamic attempt 1 is measurement-unknown because conforming T7
  behavior retained the external route and supplied no fallback target to the
  frozen P5 selector; T6 r5 Legacy attempts 1 and 2 remain preserved environment
  failures, and all older exclusions remain preserved
  `p5_t1_hover_pair_r1` (Offboard valid; Dynamic
  attempts 1 and 2 are measurement-unknown with 18 and 17 retained clock
  samples); no v4 pair is accepted
- Pending paired cells: nine untouched pairs (`p5_t7_turn_pair_r2-r5` and
  `p5_t8_descent_pair_r1-r5`); no v3 or v4
  side is reused across the observation-capture revision
- Known environment failures: three recovered v3 Dynamic T1 PX4
  abort/incomplete attempts plus v4 pilot attempt 1, which failed before PX4
  readiness because a relative artifact root was resolved inside the PX4
  subshell, plus v5 r4 Offboard attempt 1 (`timeout in TAKEOFF`, PX4 SIGABRT);
  v5 T2 r3 Offboard attempt 2 timed out in `RELEASE_OFFBOARD`; v5 T6 r5 Legacy
  attempts 1 and 2 returned 1 with invalid/degraded clock bridges after
  behaviorally complete runs; T7 r1 Legacy attempt 1 exited before required
  artifacts were available; all are preserved as environment evidence, never
  SUT or Oracle violations
- Revision blocker: T7 is `liveness_on_setpoint_off` and correctly retains the
  external route, but frozen `selected_modes()` requires an observed fallback
  for every T4–T8 run; retrying cannot produce both conforming behavior and the
  required selected Oracle result. See `P5_V5_REVISION_BLOCKER.md`.
- Next exact action: review and preregister a minimal retained-route T7
  measurement/acceptance revision. Do not resume v5 or create v6 until that
  revision is explicitly authorized, implemented, tested, and piloted.
- Last update: 2026-07-18T05:10:13-07:00
