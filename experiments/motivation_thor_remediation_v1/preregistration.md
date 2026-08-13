# Supplemental preregistration

## Purpose and separation

This study evaluates only the two cells whose primary plans could not produce
admissible evidence. It is a new formal study with a separate environment ID,
seed range, raw directory, compact results, and append-only ledger. It does not
alter, replace, or add attempts to the primary study.

The first cell tests an adjacent Land request 250 ms before the executor's
nominal completion. The public request may legitimately preempt completion, so
completion is not required. Route installation, adjacent timing and order, the
Land successor, terminal state, and every other frozen Oracle obligation remain
required.

The second cell establishes an airborne RTL source through public arm, takeoff,
and RTL commands. Only after RTL is observed and held does it request Offboard.
Completion returns to RTL, and a second observed RTL source produces the second
Offboard request. Exactly two distinct, complete route instances are required.
No PX4 internal state is written.

## Frozen contracts

The primary method thresholds and 20 ms clock bound are unchanged. Both cells
are timing-sensitive: each targets 10 accepted evidence sets and has a cap of
20 formal launches. Every launch is registered before startup and consumes the
cap regardless of outcome. Qualification data is excluded from the formal
numerator, denominator, ledger, and conclusions.

The previously qualified four-slot isolation contract is retained: CPU sets
`0-2`, `3-5`, `6-8`, and `9-13`, 24 GiB per slot, and separate PX4, Gazebo,
ROS, XRCE, port, directory, and process identities. Because this matrix has two
cells, at most two attempts run in one batch; slot rotation remains enabled.

## Frozen identities

- runtime revision: `221b9893f534b520c9d8c9728ff1805bc34f4264`;
- image ID: `sha256:d464efc84c02cc467571671d7f3aa8f7eb3c29d14c719dfe299741b3dae580c2`;
- environment ID: `thor-r38.2.1-family-a-remediation-v1`;
- formal cells: 2;
- combined accepted target: 20;
- combined launch cap: 40;
- formal concurrency contract: 4, with at most 2 active attempts in this matrix.
