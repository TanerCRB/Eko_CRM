# Architecture-sensitive paths

The task command reads this file through `scripts/risk-check.sh` (`.claude/commands/task.md`,
"Fast lane: when the Architect is skipped", step 14 and gate 2). A task touching any path below
always goes through the Architect, and its risk classes decide whether the Security Auditor runs
and whether a surviving mutation may be let through. A path missing from this list is a path the
fast lane will wave through — when in doubt, add it.

Paths follow the layout fixed by ADR-0001 and ADR-0002. Rows marked "pending
ADR-0003/0004/0005/0006" are governed by decisions not yet accepted; each of those tasks edits its
own rows.

| Path (glob) | Risk classes | Governing decisions | Why it's sensitive |
|---|---|---|---|
| `backend/app/data/**` | schema, personal-data | ADR-0002; personal-data pending ADR-0005 | persistence of contacts and customer records |
| `backend/migrations/**` | schema | ADR-0002 | expand → deploy → contract |
| `backend/alembic.ini` | schema | ADR-0002 | migration tool configuration, where revisions are found |
| `backend/app/auth/**` | auth | pending ADR-0003 | authentication, the shared access dependency, permissions |
| `backend/app/api/**` | auth, personal-data | ADR-0001; pending ADR-0003, ADR-0005 | every endpoint is an access decision over personal data |
| `backend/app/main.py` | auth | ADR-0001; pending ADR-0003 | wires the app-wide access dependency and the error handling |
| `backend/app/domain/**` | personal-data | ADR-0001; pending ADR-0005 | the contact model and what it keeps out of logs |
| `backend/app/services/**` | personal-data | ADR-0001; pending ADR-0005 | every read and write of contacts goes through here |
| `frontend/src/**` | personal-data | ADR-0001; pending ADR-0003, ADR-0005 | renders contacts and will carry the session token |
| `backend/app/core/settings.py` | secrets | ADR-0001; pending ADR-0004 | the one place configuration and secrets are read |
| `backend/app/core/**` | secrets | ADR-0001; pending ADR-0004 | configuration code beside settings.py |
| `backend/app/integrations/**` | external, personal-data | ADR-0001; pending ADR-0005, ADR-0006 | adapters to external systems receive personal data |
| `backend/pyproject.toml` | dependencies | ADR-0001 | backend package manifest |
| `backend/*.lock` | dependencies | ADR-0001 | backend lock file (`uv.lock`) |
| `frontend/package.json` | dependencies | ADR-0001 | frontend package manifest |
| `frontend/pnpm-lock.yaml` | dependencies | ADR-0001 | frontend lock file |
| `frontend/vite.config.*` | secrets | ADR-0001 | `VITE_*` values end up in the public bundle |
| `**/.env*` | secrets | pending ADR-0004 | environment configuration |
| `.env*` | secrets | pending ADR-0004 | environment files at the repository root (`**/.env*` needs a slash) |
| `**/Dockerfile*` | dependencies | ADR-0001; pending ADR-0004 | container images |
| `Dockerfile*` | dependencies | ADR-0001; pending ADR-0004 | container images at the repository root (`**/Dockerfile*` needs a slash) |
| `*compose*.y*ml` | dependencies, secrets | pending ADR-0004 | container composition |
| `.dockerignore` | secrets | ADR-0001; pending ADR-0004 | what enters the image build context at the root (`**/.dockerignore` needs a slash) |
| `**/.dockerignore` | secrets | ADR-0001; pending ADR-0004 | what enters the image build context; a dropped `.env` line bakes secrets into an image |
| `frontend/index.html` | dependencies, personal-data | ADR-0001; pending ADR-0003, ADR-0005 | a script tag here runs in the SPA beside personal data and the session token |
| `frontend/public/**` | dependencies, personal-data | ADR-0001; pending ADR-0003, ADR-0005 | static files served unbundled from the SPA's origin |
| `.npmrc` | dependencies, secrets | ADR-0001 | registry, ignore-scripts, auth tokens at the repository root (`**/.npmrc` needs a slash) |
| `**/.npmrc` | dependencies, secrets | ADR-0001 | registry, ignore-scripts, auth tokens |
| `frontend/pnpm-workspace.yaml` | dependencies | ADR-0001 | onlyBuiltDependencies, overrides, catalogs |
| `**/.pnpmfile.cjs` | dependencies | ADR-0001 | pnpm install hooks run arbitrary code and rewrite manifests |
| `backend/uv.toml` | dependencies | ADR-0001 | package index URL and resolver settings |
| `uv.toml` | dependencies | ADR-0001 | uv also reads a uv.toml from parent directories |
| `**/ruff.toml` | pipeline | ADR-0001 | per-layer banned-api config (ADR-0001-C11); weakening it silently drops layer enforcement |
| `ruff.toml` | pipeline | ADR-0001 | ruff config at the repository root (`**/ruff.toml` needs a slash) |
| `.ruff.toml` | pipeline | ADR-0001 | ruff config at the repository root; takes precedence over `ruff.toml` in its directory |
| `**/.ruff.toml` | pipeline | ADR-0001 | ruff config; takes precedence over `ruff.toml` and `pyproject.toml` in its directory |
| `frontend/tsconfig*.json` | pipeline | ADR-0001 | `strict` (ADR-0001-C3) |
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
