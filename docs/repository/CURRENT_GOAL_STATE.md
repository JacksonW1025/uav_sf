# Current Goal state

- Goal phase: Phase B, P5 retained-route candidate revision complete
- Historical P5 Differential Gate: `INCONCLUSIVE`; no new gate is claimed
  because no formal successor campaign has been created
- Frozen campaign: `campaign_seeded_v5` remains permanently
  `CLOSED_REVISION_CHANGE_REQUIRED`, with 25/35 complete pairs, 50 accepted
  sides, partial T7 r1, and nine untouched T7/T8 pairs; its manifest SHA-256
  remains `8c7727986...329c31f`
- Retained-route contract: `p5-retained-route-observation-v1` / `1.0`,
  preregistered and reviewed; T7 is `RETAINED_ROUTE`, while T1/T2/T4/T5/T6/T8
  remain `TRANSITION`
- Candidate implementation: commit `7f736c209b2818dc0d64024ffd6045c8549f0e13`;
  Route Oracle `0.4`, result schema `1.3`, trace schema unchanged at `1.2`,
  scenario schema `1.1`, unchanged `route-oracle-v0.3-default` thresholds
- Candidate identity: PX4 `4ae21a5e...`, binary `931320a0...`, observation patch
  `73555576...`, adapter binary `af5a02a2...`, scenario hash `e0affa...b3db5`,
  contract hash `41be4c...90e4c`, and unchanged Hold fallback parameters; canonical
  snapshot: `experiments/probes/p5/retained_route_candidate_identity.json`
- Focused tests: PASS, `38 passed`; complete repository validator: PASS,
  `125 passed` before revision-2 pilots and at final handoff
- Offline v5 regression: saved Dynamic T7 attempt produces candidate Oracle
  PASS/COMPLETE without a fallback requirement, but remains historical v5
  `MEASUREMENT_UNKNOWN`; no v5 record was backfilled
- Transition regression: accepted v5 T5 Legacy transition selection, overall
  status, and all clause statuses are unchanged under Oracle 0.4
- Legacy T7 candidate pilot: revision 2 attempt 1 VALID; runner/monitor PASS,
  VALID clock (33 samples, 37.233 ms max residual), COMPLETE 3000 ms window,
  mode 14/epoch 3 retained, 12 ms maximum gap, zero violation counts, exact
  clause applicability, identity match
- Dynamic T7 candidate pilot: revision 2 attempt 1 VALID; runner/monitor PASS,
  VALID clock (35 samples, 65.374 ms max residual), COMPLETE 3000 ms window,
  mode 23/epoch 4/activation 2 retained, 12 ms maximum gap, zero violation
  counts, exact clause applicability, identity match
- Preserved sensitivity attempts: candidate revision-1 Legacy attempts 1 and 3
  were environment failures with DEGRADED clocks; attempt 2 was
  `MEASUREMENT_UNKNOWN` because Legacy trace composition omitted preserved
  monitor markers. Revision 2 merged that existing evidence without changing
  patch, schema, monitor, window, threshold, or SUT behavior; no revision-1 side
  was reused
- Authorization recommendation: `AUTHORIZED_FOR_V6_CREATION`
- Formal v6 status: not created; no official v6 case or matrix has run
- Next exact action: Review candidate revision report and explicitly authorize
  creation of `campaign_seeded_v6`.
- Last update: 2026-07-18T08:27:04-07:00
