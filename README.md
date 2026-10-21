# Eko_CRM

CRM application. Monorepo: `backend/` (Python, FastAPI) and `frontend/` (React + TypeScript).

Developed with the Ninefold process (AI-agent SDLC with three human gates) — start with
[`CLAUDE.md`](CLAUDE.md) and [`TEAM-CONTRACT.md`](TEAM-CONTRACT.md).

After cloning:

```bash
git config core.hooksPath .githooks     # the pre-push guard on main
node tools/sync-agents.mjs              # copies agents/ into .claude/agents/
```

Licensing of the process material (`FrameworkDoc.md`, `agents/`, `process/`, `scripts/`,
`tools/`, `calibration/`): Apache License 2.0, see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
