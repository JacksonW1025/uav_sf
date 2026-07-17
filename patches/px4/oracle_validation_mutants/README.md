# PX4 Oracle validation mutants

These patches are **TEST-ONLY ORACLE VALIDATION MUTANTS** and must never be
used as the canonical SUT. `mc_pos_control_route_mutants.patch` adds three
SITL-only, environment-selected data-path faults to a separate PX4 worktree:

- `install_delay`: discards new trajectory setpoints for a bounded interval on
  Offboard entry;
- `recovery_incomplete`: clears the previous input and discards fallback
  trajectory setpoints for a bounded interval on Offboard exit;
- `old_route_late_consumption`: retains the last Offboard setpoint as the real
  position-controller input after exit and emits consumption evidence carrying
  the cached subject timestamp.

The build has no active mutant unless `UAV_SF_ORACLE_MUTANT_MODE` is set.
`UAV_SF_ORACLE_MUTANT_DELAY_MS` selects the bounded interval. Ordinary setup
scripts never reference the mutant worktree.
