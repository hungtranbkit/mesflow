# MESFlow — QC Agent Test-Case Generation: Handoff

**You are about to generate test cases for MESFlow.** Read this file
first (2 minutes), then read `docs/MESFLOW_MASTER_REQUIREMENTS.md` in
full before writing a single test case. This file does not duplicate
that one — it only tells you how to use it.

## What you have and don't have

You have **only** `docs/MESFLOW_MASTER_REQUIREMENTS.md`. You do not
have, and must not assume, access to MESFlow's source code, a running
instance, or any prior conversation about this system. The master
document was written specifically so that this is enough — every
formula, state machine, permission rule, sample dataset, and error
message a test case needs is written out in full there, not referenced
as "see the code."

## How to generate test cases

1. Read the master document's Part A (§1–§14) once, in full, before
   touching Part B — the appendices are the shared reference every
   requirement points back to (RBAC matrix, entity fields, state
   machines, KPI formulas, exception rules, sample data, etc.).
2. Work through Part B (`REQ-*`) one requirement at a time. For each
   one, apply the master document's own §20.2 generation rule: produce
   a positive case, one negative case per distinct validation/error
   rule, one case per named boundary, RBAC cases per the requirement's
   Permission field, a state-transition case where applicable, and a
   concurrency case only where the requirement's Concurrency field is
   not `N/A`.
3. Do the same for Part C (`BR-*`) business rules that aren't already
   fully covered by a `REQ-*` case.
4. Use Part D (UI/UX) only for page-level responsive/empty-state/UI
   checks — apply the 3-viewport matrix (REQ-UI-006) to every screen
   Part B introduces.
5. Use Part E's journeys as ready-made E2E test cases — convert each
   numbered step directly into a `Steps`/`Expected Result` pair.
6. Check Part F (traceability) before assuming a case needs writing
   from scratch — if a requirement already shows "A" (automated
   coverage exists), your generated case is a **specification** of
   what that coverage should assert, not necessarily new work; if it
   shows "—" or "P", treat it as higher priority to actually write.
7. **Never invent a fact.** If a requirement's field says `N/A
   confirmed` or points to Part H (`SPEC-GAP-*`/`OPEN-QUESTION-*`),
   write a test case that **checks and records actual behavior**
   rather than asserting a guessed expected result. Do not silently
   resolve a gap by picking whichever answer seems more likely.

## Output format — use exactly this, every time

```
TC-ID:              TC-<MODULE>-<###>
Requirement ID:      REQ-... and/or BR-...
Title:               one-line description of what this specific case checks
Priority:            P0 | P1 | P2
Type:                positive | negative | boundary | RBAC | state-transition | concurrency | recovery | responsive
Preconditions:       exact starting DB/session state
Test Data:           concrete values from §13 of the master doc, or fully specified inline
Steps:               numbered, one observable action per step
Expected Result:     one expectation per step, or one combined final-state expectation — objectively checkable
Postconditions:      state to leave the environment in / cleanup needed
Environment:         which tier (§12 of the master doc)
Role:                which persona (§13.1 of the master doc)
Automation Candidate: Yes | No
```

**Naming convention**: `TC-<MODULE>-<###>`, module code matches the
requirement's own ID prefix (`AUTH`, `PO`, `SESS`, `KIOSK`, `EXC`,
`PROD`, etc. — full list in the master doc's §20.1). Number
sequentially per module, zero-padded to 3 digits, never reuse a number
even for a later-removed case.

## Before you submit any test case, self-check

- Does every value in `Test Data`/`Steps` trace back to §13 of the
  master doc, or is it fully specified with no unresolved "an existing
  record" / "the current data" reference?
- Does `Expected Result` state an exact, checkable value (status code,
  field value, enum, message string) rather than a subjective
  judgment?
- If this case covers a `SPEC-GAP`/`OPEN-QUESTION` from Part H, does it
  say so explicitly rather than silently assume an answer?

If any answer is "no," fix the case before moving on — do not submit
it and hope a human catches it later.
