# Safety Policy

## Current authorization

Milestones 0 and 1 authorize research and observe-only market-data operation. They contain no funded, live, paper-order, or DEMO-order authorization. MT5 DEMO execution remains disabled and non-operational.

## Non-negotiable controls

- AI components have no direct broker authority.
- Strategy code cannot mutate broker state or call `MetaTrader5.order_send`.
- Execution adapters remain downstream of portfolio, risk, and explicit authorization checks.
- MT5 DEMO use must verify the account as DEMO before any future mutation.
- REAL, FUNDED, CONTEST, and UNKNOWN account types fail closed.
- An unavailable or ambiguous account classification is `UNKNOWN`, never DEMO.
- Configuration defaults to `OBSERVE_ONLY`.
- Strategies receive no execution authorization by default.
- Secrets, credentials, tokens, and private paths must never enter source control or logs.
- Safety failures must reject action and emit an auditable reason.

## Promotion policy

No strategy may automatically move from RESEARCH to SHADOW, PAPER, or DEMO. A future promotion process must require independent evidence, version pinning, explicit human approval, and regression tests. Milestone 1 provides no route to DEMO, REAL, funded, contest, or unknown-account mutation.

## Incident posture

If data is stale, spread is abnormal, a signal is duplicated, strategies conflict, session control rejects trading, macro-event status is unclear, or account type cannot be verified, the system must reject execution.
