# External mode and registration evidence

Status: `not_collected`

Use this document for M2 source-backed evidence. Do not replace missing evidence with assumptions.

## Source record template

| Field | Value |
|---|---|
| Source URL or repository path | TBD |
| Source version / commit | TBD |
| Accessed date | TBD |
| PX4 component | TBD |
| Lifecycle stage | registration / activation / execution / cancellation / failure / recovery / re-entry |
| Claim supported | TBD |
| Control-plane signal | TBD |
| Data-plane signal | TBD |
| Route fields affected | TBD |
| Existing official test | TBD |
| Confidence / caveat | TBD |

## Questions to resolve

- What makes an external mode/controller registered, eligible, active, and no longer active?
- Which system owns authority at each lifecycle boundary?
- What producer and writer identities should change during activation/cancellation/failure?
- What timeouts and freshness requirements trigger revocation or fallback?
- Does fallback selection prove that all target modules and writers were restored?
- Can re-entry retain stale registrations, subscriptions, setpoints, or writer state?

## Evidence log

No entries collected yet.
