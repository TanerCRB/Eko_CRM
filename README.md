# Eko_CRM

CRM application. Monorepo: `backend/` (Python, FastAPI) and `frontend/` (React + TypeScript).

Developed with the Ninefold process (AI-agent SDLC with three human gates) — start with
[`CLAUDE.md`](CLAUDE.md) and [`TEAM-CONTRACT.md`](TEAM-CONTRACT.md).

After cloning:

```bash
git config core.hooksPath .githooks     # the pre-push guard on main
node tools/sync-agents.mjs              # copies agents/ into .claude/agents/
```

## Run the development profile

Needs Docker Engine with Compose v2, and bash (Git Bash on Windows) for the first line.

```bash
bash scripts/dev-env.sh ../eko-dev.env   # once: an untracked file of synthetic values, outside the checkout
docker compose --env-file ../eko-dev.env --profile dev up --build --wait
```

The application answers at `https://localhost:8443/` (certificate from Caddy's internal CA), its
health route at `https://localhost:8443/api/health`. Stop with
`docker compose --env-file ../eko-dev.env --profile dev down`; add `-v` to delete the data volumes.
Without `--profile dev` the same file is the shared-environment composition (no mail catcher).

The environment file also names this checkout's Compose project and backend image tag, so each
worktree needs its own file (for example `../eko-dev-<identifier>.env`) and two worktrees run side
by side without sharing containers, volumes or images. If `postgres` reports that a volume's first
initialisation did not complete, run `down -v` and start again.

Licensing of the process material (`FrameworkDoc.md`, `agents/`, `process/`, `scripts/`,
`tools/`, `calibration/`): Apache License 2.0, see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
