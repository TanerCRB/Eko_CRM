# Working agreement for AI agents

This repository uses the Ninefold SDLC process. Follow the project process rather than a generic implementation workflow.

## Read first

1. `TEAM-CONTRACT.md` — roles, human gates and hard stops; governs over role files on discrepancy.
2. `process/sdlc-flow.md` — Issue states and transitions.
3. `.claude/commands/task.md` — the complete task procedure, including checkpoints and evidence rules.
4. `docs/PLAN.md` — task scope and completion conditions.
5. `docs/architecture/capabilities.md` and `docs/architecture/decisions/` — proven capabilities and accepted architecture decisions.

Use `.claude/commands/task.md` as the operational checklist when driving an Issue. Use `.claude/commands/task-status.md` for read-only status reports.

## Non-negotiable rules

- Status is raised by evidence, not conviction. Never check off a task or raise a capability status yourself.
- Gates 1, 2 and 3 belong to the human. Prepare the material and stop; never remove `waiting-on-human` yourself.
- Do not start production work without acceptance criteria and either an architecture impact map or an approved fast-lane record.
- After gate 1, preserve the scope lock. A changed Definition of done, Out of scope or acceptance criterion sends the task back to gate 1.
- A task that writes code uses its own branch and worktree. Allow only one writing session per working tree and stop if another session already holds the task.
- Do not commit, push or merge without an explicit request, except the pre-authorized local commits listed in `.claude/commands/task.md`. Never merge a pull request yourself.
- Write tests before the implementation they prove and observe them failing first. Never weaken, skip or remove a failing test to make a change pass.
- QA evidence requires a contrast test and an executed mutation. All evaluation reports must refer to the same `VERIFIED` SHA.
- The code PR says `Refs #N` and leaves the Issue open. Only the separate gate-3 documentation PR says `Closes #N`.
- Artifacts — code, comments, documentation, Issues, PRs and commits — are in English unless the human explicitly chooses otherwise. Reply in the human's language.
- Run shell process scripts through Git Bash: `bash scripts/<name>.sh`.

## Stop and ask

Stop work and ask the human when a task requires deviation from an accepted architecture decision, a schema change outside a migration, work on personal data without a covering decision, resolution of a non-mechanical merge conflict, or handling of an existing test broken by the change. Also stop on failed write-boundary or scope checks, missing evidence, and the fix-round limit defined by the task procedure.

## Verification and reporting

Run the quality gates required by `.claude/commands/task.md` for every touched side of the repository. Treat a check that could not run as unverified, never as passed. Reports must distinguish executed checks from unchecked claims and link completion evidence rather than declaring readiness from implementation alone.
