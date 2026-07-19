# Current Goal state

- Current phase: External RTL successor motivation study, primary reproduction
  preregistered; attempt-1 observability correction ready for checkpoint before
  the next bounded baseline run
- Goal disposition: active, no terminal disposition yet
- Primary reproduction target: Auterion/px4-ros2-interface-lib Issue #162,
  External RTL replacement selected while its owning Mode Executor remains
  Autopilot, preventing the expected Land successor
- Baseline status: repository recovery PASS; existing P0-C is not reused
  because it predates the current Loiter-replacement mode semantics and lacks
  complete executor-in-charge, public completion, and successor-command
  evidence; the separate non-replacement `Successor Baseline` executor now
  implements Takeoff → owned External Mode → completion → Land → Disarm, but
  first successor flight attempt completed the physical chain but was rejected
  for an observer/profile defect and insufficient clock samples; accepted count
  remains `0/3`
- Observability status: lifecycle event schema 1.0 and a dedicated monitor now
  cover registration, active/owned mode, executor in charge, completion,
  successor command, Land selection, landed state, Disarm, and clock samples;
  the route collector now preserves component-declared identity; live
  validation remains pending
- Successor Oracle status: version 0.1 implemented independently of Route
  Oracle 0.4; nine focused synthetic tests cover PASS, Issue #162 ownership
  and missing-successor violations, completion loss, wrong requester,
  route-UNKNOWN conservatism, missing evidence, and NOT_APPLICABLE; live
  attempt 1 exposed and corrected the request encoding to
  `VEHICLE_CMD_SET_NAV_STATE(100001), param1=Land(18)`; live PASS remains pending
- Current-version reproduction status: not started; source audit predicts
  construction-time rejection because locked px4-ros2-interface-lib
  `c3e410f` contains guard commit `dce6c1f`
- Historical reproduction status: not started; reported affected target is
  px4-ros2-interface-lib `release/1.16` / `a5b9f3c`
- Probe status: none; no primary reproduction or bounded motivation probe has run
- Confirmed issue count: 0 local reproductions; one upstream-confirmed
  unsupported ownership/successor lifecycle selected for reproduction
- Current blocker: none; baseline attempt 1 is preserved and classified
  `REJECTED_OBSERVABILITY`, never as a lifecycle violation
- Next exact action: publish the evidence-driven request-encoding and observer
  tail correction, then retry seed `16201` under a new attempt ID without
  changing thresholds or acceptance criteria
- Motivation namespace: `experiments/motivation/successor/`,
  `runs/motivation/successor/`, and
  `data/processed/motivation/successor/`; P5 v6 remains frozen and isolated
- Baseline attempt ledger:
  `experiments/motivation/successor/baseline_attempt_ledger.yaml`; attempt 1
  monitor PASS, clock INVALID (18/20 usable samples), Route Oracle UNKNOWN,
  attempt-time Successor Oracle VIOLATION caused by the corrected command match
- Motivation-study baseline validation: focused PASS (`38 passed`); full PASS
  (`125 passed`, `15/15` stages)
- Baseline harness build: PASS against locked Humble px4-ros2-interface-lib;
  executable SHA-256
  `eba79e78565587a71cac2e5a70677f9c88ca4172054483beb2fc40414bdccc45`;
  locked library SHA-256
  `dddfa0698c27617ce5a368dc7d0d5272bc510f3cb780c5ef3f48c77d098380e6`
- Last motivation checkpoint validation: focused PASS (`22 passed` for the
  successor/trace contracts); full PASS (`139 passed`, `15/15` stages)
- Protected P5 v6 hashes at Goal start: differential Gate
  `9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc`;
  manifest
  `02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518`
- Primary preregistration:
  `experiments/motivation/successor/primary_reproduction_preregistration.yaml`
- Successor Oracle design: `docs/design/SUCCESSOR_PROGRESSION_ORACLE.md`
- Last update: 2026-07-19T05:46:16-07:00

## Preserved P5 v6 completion state

- Goal phase: Phase B, formal P5 v6 paired campaign completed and analyzed
- `campaign_seeded_v6` status: `COMPLETE_ANALYZED`; formal campaign,
  authorized by `AUTHORIZED_FOR_V6_CREATION`
- P5 Differential Gate: `CONDITIONAL_PASS`
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
- Matrix progress: 35 complete pairs, 0 partial pairs, 0 pending pairs;
  70 accepted sides, 0 excluded attempts, 25 environment failures, 0 campaign
  configuration failures
- Last completed pair: independent-fallback cell `p5_t8_descent_pair_r5`;
  both attempt 1 sides are accepted with seed `50805`,
  health off/setpoint on, independently observed Hold fallback, `COMPLETE`
  transition windows, and PASS on all applicable clauses
- Current partial pair: none
- Accepted-evidence audit: 70 return-0, scenario-PASS, clock-VALID,
  complete-window, exact-identity, Oracle-PASS sides; 60 `TRANSITION` and 10
  `RETAINED_ROUTE`; zero accepted UNKNOWNs or violations
- Paired analysis: 71 preregistered comparisons; no timing difference resolved
  above combined clock uncertainty. T4 turn/graceful-shutdown peak tilt is the
  sole measurable signal (Dynamic minus Legacy median `0.007939 rad`, 95% CI
  `[0.004781, 0.008803]`, resolution `0.001414 rad`), but its `0.2115` CV
  triggers adaptive confirmation.
- T7 summary: all ten sides health-on/setpoint-off, `COMPLETE` 3000 ms retained
  windows, continuity/exclusivity PASS, other three clauses
  `NOT_APPLICABLE`, and no fallback, route change, disallowed gap, authority
  conflict, or writer conflict
- T8 summary: all ten sides health-off/setpoint-on and independently observed
  Hold fallback with `COMPLETE` transition windows and all clauses PASS
- Adaptive analysis: `INCREASE_TRIGGERED_CELLS_TO_MAXIMUM` for all seven cells;
  carried as a Gate condition and future-study recommendation because the
  explicitly authorized v6 matrix stops at five repeats / 35 pairs
- Environment diagnosis: elevated host scheduling load (10.62/9.79/9.25) is
  present, with remote-desktop and GUI CPU load but no experiment residue,
  occupied campaign port, memory exhaustion, or workspace disk pressure;
  classification remains transient run-environment instability, not
  frozen-revision drift
- Next exact action: review the `CONDITIONAL_PASS` report/Gate and separately
  authorize a scoped next-phase design if desired; do not add v6 cases or
  start next-stage execution under this Goal
- Historical campaigns: `campaign_seeded_v3` and `campaign_seeded_v4` remain
  preserved/closed; `campaign_seeded_v5` remains permanently
  `CLOSED_REVISION_CHANGE_REQUIRED` with 25/35 complete pairs, 50 accepted
  sides, one partial T7 pair, and nine untouched T7/T8 pairs
- v5 manifest preservation: SHA-256
  `8c7727986b2b0200f19e5983be8fc25177d07b9ab0e97c10740525a6e329c31f`;
  v5 records and candidate pilot sides are not reused
- Baseline focused retained-route tests: PASS, `38 passed`
- Baseline full repository validator: PASS, `125 passed`, `15/15` stages
- Current blocker: none; no frozen-revision blocker
- Last checkpoint focused tests: PASS, `38 passed`
- Last checkpoint full repository validator: PASS, `125 passed`, `15/15`
  stages
- Formal report: `docs/repository/P5_V6_DIFFERENTIAL_REPORT.md`
- Machine Gate: `experiments/probes/p5/p5_v6_differential_gate.json`
- P5 v6 last update: 2026-07-18T15:13:51-07:00
