---
name: ship
description: Plan, build, adversarially review until the reviewer approves, verify like a user, then present. Never a first draft.
argument-hint: <what to build or change>
---

Ship this change to Reckon, following the definition of done in CLAUDE.md. Do not present a first draft. Do not skip a step because the change looks small.

Task:

$ARGUMENTS

## 1. Plan
If the change is non-trivial (more than a tiny edit), enter plan mode and get the plan approved before writing code. State what you will change, which files, and how you will test the new behavior. For a trivial change, say why it is trivial and proceed.

## 2. Build
Implement the change. Write or update tests that exercise the new behavior, including its failure mode, not just the happy path. Keep any new warehouse SQL working on both Postgres and Redshift (quoted `"raw"`, no `FILTER (WHERE)`, no `now()` default). No em dashes, sentence case headings.

## 3. Adversarial review, loop until approved
Invoke the `reviewer` subagent on the diff. Fix every BLOCKER. Re-invoke the reviewer. Repeat until the verdict is APPROVE. Do not talk the reviewer into approving, fix the code. Never ship while a BLOCKER stands.

## 4. Verify like a user
Run the suites the change touches (`make test`, the copilot subset, `npm test`, `dbt parse`). For a UI change, run `make local`, open the dashboard at http://localhost:5173, confirm the change renders, and capture a screenshot. Then `make local-down`.

## 5. Present
Summarize what changed, the tests you added and ran with their results, the reviewer's final verdict, and the exact commands to reproduce. Commit and push (uncommitted work does not exist). The Stop hook will not let you finish while `ingest/tests` fail.
