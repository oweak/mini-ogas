# Mini-OGAS Engineering Rules

## Mission

Mini-OGAS is a VM-level distributed industrial production and operations
simulation prototype. It is not a production MES and must never present mock,
seed, fallback, replay, or local-process data as a real distributed deployment.

## Fact Ownership

- SimPy and Edge Agents generate production facts.
- PostgreSQL owns historical facts.
- Redis may cache current state only after it is introduced and verified.
- NATS may transport events only after it is introduced and verified.
- Central API coordinates queries and controlled actions.
- Dashboard displays backend facts and submits controlled requests; it does not
  generate operational truth.
- Rules and optimization code perform deterministic calculations.
- LLMs explain evidence and propose actions; they do not alter facts or bypass
  Safety Governor, approval, Command Manager, or Verifier.

## Completion Standard

A capability is complete only when implementation, caller, failure handling,
automated tests, runtime evidence, and documentation agree. Classify every
capability as A (implemented and runtime-verified), B (implemented but not
runtime-verified), C (shell/interface only), D (documentation only), or E
(broken/invalid). Never promote a capability using code presence alone.

## Control Path

Every state-changing action follows:

```text
proposal -> Safety Governor -> approval when required -> Command Manager
-> Edge Agent idempotent execution -> result -> Verifier observation
-> effective | partial | failed | inconclusive
```

Agent success is an execution acknowledgement, not proof of operational effect.
The Verifier must use subsequent observed facts.

## Engineering Discipline

- Preserve unknown user changes and inspect `git status` before editing.
- Do not expose `.env` values, tokens, credentials, or AI keys.
- Do not use `git reset --hard`, rewrite history, or push without permission.
- Prefer targeted searches and repository-native patterns.
- Use PostgreSQL for central runtime facts; SQLite is limited to tests and edge
  buffering.
- Keep live, replay, mock, degraded, and stale states explicit in API and UI.
- Keep compatibility wrappers thin, deprecated, tested, and listed with exit
  conditions in `docs/ARCHITECTURE_DEBT.md`.
- Run the smallest relevant tests after each unit and
  `scripts/verify-miniogas.ps1` at phase boundaries.
- Update `docs/CODEX_PROGRESS.md`, `docs/VERIFICATION_MATRIX.md`, and
  `docs/CODEX_HANDOFF.md` with actual commands and results before stopping.

## Safety Boundary

Red-team activity is restricted to explicitly authorized local lab targets.
No public scanning, third-party targets, persistence malware, host damage, or
credential leakage is permitted. High-risk commands require approval and audit.
