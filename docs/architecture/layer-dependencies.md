# Layer dependencies

The task command reads this file through `scripts/layer-check.sh` (`.claude/commands/task.md`,
step 10a, "Layer check"). Each row names one layer: where its files live, how other code refers to
it, and which layers it **must not depend on**. Format rules: `process/registers/layer-dependencies.md`.

**Provisional.** No code exists yet; the layout below is the one planned for the first decisions
(EKO-1-01). The Architect revises it when ADR-0001 is accepted.

| Layer | Path (glob) | Referenced as | Must not depend on | Why |
|---|---|---|---|---|
| `domain` | `backend/app/domain/**` | `app.domain` | services, data, api | pending ADR-0001: the domain knows no storage and no transport |
| `services` | `backend/app/services/**` | `app.services` | api | pending ADR-0001: use cases don't know HTTP |
| `data` | `backend/app/data/**` | `app.data` | services, api | pending ADR-0002: persistence is called, it doesn't call in |
| `api` | `backend/app/api/**` | `app.api` | — | the outermost backend layer |
| `fe-api` | `frontend/src/api/**` | `@/api` | fe-components, fe-features | the typed client knows no UI |
| `fe-components` | `frontend/src/components/**` | `@/components` | fe-api, fe-features | presentational components don't fetch |
| `fe-features` | `frontend/src/features/**` | `@/features` | — | screens compose the client and the components |
