# Architecture-sensitive paths

The task command reads this file through `scripts/risk-check.sh` (`.claude/commands/task.md`,
"Fast lane: when the Architect is skipped", step 14 and gate 2). A task touching any path below
always goes through the Architect, and its risk classes decide whether the Security Auditor runs
and whether a surviving mutation may be let through. A path missing from this list is a path the
fast lane will wave through — when in doubt, add it.

**Provisional.** No code exists yet; the paths below follow the layout planned for the first
decisions (EKO-1-01). The Architect revises them when ADR-0001/ADR-0002 are accepted.

| Path (glob) | Risk classes | Governing decisions | Why it's sensitive |
|---|---|---|---|
| `backend/app/data/**` | schema, personal-data | pending ADR-0002 | persistence of contacts and customer records |
| `backend/migrations/**` | schema | pending ADR-0002 | expand → deploy → contract |
| `backend/app/auth/**` | auth | pending | authentication, the shared access dependency, permissions |
| `backend/app/api/**` | auth, personal-data | pending ADR-0001 | every endpoint is an access decision over personal data |
| `backend/app/core/settings.py` | secrets | pending ADR-0001 | the one place configuration and secrets are read |
| `backend/app/integrations/**` | external, personal-data | — | adapters to external systems receive personal data |
| `backend/pyproject.toml` | dependencies | — | backend package manifest |
| `backend/*.lock` | dependencies | — | backend lock file |
| `frontend/package.json` | dependencies | — | frontend package manifest |
| `frontend/pnpm-lock.yaml` | dependencies | — | frontend lock file |
| `frontend/vite.config.*` | secrets | — | `VITE_*` values end up in the public bundle |
| `**/.env*` | secrets | — | environment configuration |
| `**/Dockerfile*` | dependencies | — | container images |
| `.github/workflows/**` | pipeline | — | who runs what, with which secrets |
| `.githooks/**` | pipeline | — | the pre-push guard on `main` |
| `scripts/**` | pipeline | — | the process checks the task command and CI rely on |
| `agents/**` | model | — | role definitions: prompts that drive the agents |
| `.claude/**` | model | — | commands and permission settings of the agent environment |

**One glob per row**, in backticks (the class table below is deliberately without backticks — `risk-check.sh` reads every row whose first cell is in backticks as a path); `*` and `**` both match across directories. **Classes** are a
closed list, comma-separated:

| Class | Covers | The Security Auditor runs | A `SURVIVED` mutation may be excepted |
|---|---|---|---|
| schema | migrations, the data schema | yes | no — it is fixed |
| auth | authentication, authorization, isolation context, permission catalog | yes | yes |
| money | prices, invoices, payments, refunds | no | no — it is fixed |
| personal-data | files that read, store or send personal data | yes | yes |
| pipeline | CI/CD configuration, the runner | yes | yes |
| dependencies | package manifests, lock files, container images | yes | yes |
| secrets | configuration, environment variables, anything that looks like a secret | yes | yes |
| external | the adapter layer to external systems | yes | yes |
| model | code that calls a language model or defines its tools, prompt templates | yes | yes |

A class the script doesn't know fails the check (exit 2) instead of being ignored. If you add a
class, add it to `CLASSES` (and, where it applies, `AUDITOR_CLASSES` or `NO_EXCEPTION_CLASSES`) in
`scripts/risk-check.sh`, and a self-test case for it.
