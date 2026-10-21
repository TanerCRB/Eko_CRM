# Eko_CRM

CRM application (domain detail is TODO — filled in at gate 1 of the first Story). Monorepo:
`backend/` (Python 3.12, FastAPI, Pydantic) and `frontend/` (React + TypeScript, Vite, pnpm). No
code yet; the first task is the stack and persistence decisions (`docs/PLAN.md`, `EKO-1-01`).

This repo is also the source of its own process: a monorepo instantiation of **Ninefold**
(https://github.com/TanerCRB/NineFold, v0.10.0), an SDLC framework for AI-agent-driven development
(Spec-Driven Development + Human-in-the-Loop). Read in this order:

1. **[`TEAM-CONTRACT.md`](TEAM-CONTRACT.md)** — who does what, gates, hard stops. Governs over
   role files on discrepancy.
2. **[`process/sdlc-flow.md`](process/sdlc-flow.md)** — state machine, labels.
3. **[`docs/PLAN.md`](docs/PLAN.md)** — task register.
   **[`docs/architecture/capabilities.md`](docs/architecture/capabilities.md)** — what is proven to
   work, separate from what is decided. `docs/architecture/decisions/` — architecture decisions.
4. **[`FrameworkDoc.md`](FrameworkDoc.md)** and **[`process/`](process/)** — the general pattern
   this configuration was adapted from. Reference for *why*, not day-to-day use.

## Roles and gates

Nine role definitions in `agents/`, synced to `.claude/agents/` with `node tools/sync-agents.mjs`
(that directory is git-ignored — run the sync after editing a role, `--check` for drift). Four
evaluate (`invariant-guardian`, `reviewer`, `security-auditor`, `qa`), five produce
(`product-owner`, `analyst`, `architect`, `developer-backend`, `developer-frontend`). A role never
evaluates its own output. `/task #N` drives one task end to end (`.claude/commands/task.md`);
`/task-status #N` is the read-only report.

Three human gates, never crossed by an agent: **1** scope/architecture before code, **2** merge
into `main`, **3** merge of the separate documentation PR (`Closes #N`) that raises status in
`docs/PLAN.md` / the capability register — the code PR says `Refs #N`. `is:open
label:waiting-on-human` finds everything waiting on the human.

## Hard rules for every session in this repo

- **No `git commit`, `git push`, `git merge`, or `gh pr merge` without an explicit request** —
  except the pre-authorized bookkeeping and checkpoint commits listed in `.claude/commands/task.md`.
  `.claude/settings.json` denies `gh pr merge` and force pushes, and asks before any push.
- `main` is guarded by `.githooks/pre-push` (free plan, private repo: a guard, not a gate). Every
  clone needs `git config core.hooksPath .githooks` once.
- Artifacts (code, comments, Issues, PRs, commits, docs) in English; the conversation may be in
  Polish.
- Run the process scripts through Git Bash: `bash scripts/<name>.sh`.

## Where things live

| What | Where |
|---|---|
| Role definitions (source) | `agents/` |
| Task commands | `.claude/commands/task.md`, `.claude/commands/task-status.md` |
| Process checks (boundary, weakening, leftovers, layers, risk, scope, evidence chain, exceptions, markers) | `scripts/*.sh` — adapted copies of the kit's `process/scripts/` |
| Hooks | `.githooks/pre-push`; `scripts/task-journal-context.sh` and `scripts/cost-capture.mjs` registered in `.claude/settings.json` |
| Issue/PR templates (source) | `process/issue-templates/`, synced to `.github/` with `node tools/sync-github.mjs` |
| Frontend PR template | `.github/PULL_REQUEST_TEMPLATE/frontend.md` — copied by hand from `process/issue-templates/PULL_REQUEST_TEMPLATE-frontend.md` (the sync writes only the default backend one) |
| Labels | `process/labels.json`, applied with `node tools/sync-github.mjs --labels \| bash` |
| Registers | `docs/PLAN.md`, `docs/architecture/{capabilities,architecture-sensitive-paths,layer-dependencies,exception-register}.md`, `docs/cost-register/` |
| Tests | `backend/tests/`, `frontend/tests/` (mirrors `frontend/src/`) — never next to the code, so QA's write boundary is one prefix per side |
| Task worktrees | `../Eko_CRM-<identifier>`, branch `<identifier>-<slug>` |

`docs/architecture/layer-dependencies.md` and `architecture-sensitive-paths.md` are provisional
until ADR-0001/ADR-0002 are accepted.

Upgrading the process: `UPGRADING.md`, diffing the kit's new version against `agents/`,
`scripts/`, `.claude/commands/` and `process/`.
