# Current Goal state

- Goal phase: Phase B, P5 recovery and stabilization
- Current gate: P5 Differential Gate, initial five-pair matrix incomplete
- Current campaign: `campaign_seeded_v5` — `PENDING_CAPTURE_PILOT`; v3 and
  v4 are preserved and closed
- Repository checkpoint commit: `c38fa5743f2d1098c21c6c5c9f04538e8e9c62d4`
- Campaign revision identities: PX4 `4ae21a5e...`; PX4 binary `931320a0...`;
  observation patch `73555576...`; adapter `a02fc11` / binary `af5a02a2...`;
  Route Oracle `0.3`; trace schema `1.2`; threshold profile
  `route-oracle-v0.3-default`; scenario matrix `8a39d52f...`; Hold fallback
- Completed deliverables: Oracle Validation Gate; Oracle 0.3; P5 runner,
  matched matrix, fault markers, paired analysis, strengthened clock capture,
  recovery manifest reconstruction, and bounded batch/retry controls
- Current pilot: v4 Dynamic T5 attempt 2 is revision-matched and valid; Hold,
  clock, critical-window, epoch, revocation, writer, and all Oracle checks pass
- Completed paired cells: none
- Partial paired cells: none in v5; v4 `p5_t1_hover_pair_r1` (Offboard valid; Dynamic
  attempts 1 and 2 are measurement-unknown with 18 and 17 retained clock
  samples); no v4 pair is accepted
- Pending paired cells: the next revision must rerun all 35 pairs; no v3 or v4
  side is reused across the observation-capture revision
- Known environment failures: three recovered v3 Dynamic T1 PX4
  abort/incomplete attempts plus v4 pilot attempt 1, which failed before PX4
  readiness because a relative artifact root was resolved inside the PX4
  subshell; all are preserved as environment evidence, never SUT or Oracle
  violations
- Next exact action: checkpoint the v5 descriptor, then run exactly one Dynamic
  T1 capture pilot; begin the paired matrix only if at least 20 clock samples
  remain and all normal validity gates pass
- Last update: 2026-07-17T13:18:51-07:00
