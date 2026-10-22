# Layer dependencies

The task command reads this file through `scripts/layer-check.sh` (`.claude/commands/task.md`,
step 10a, "Layer check"). Each row names one layer: where its files live, how other code refers to
it, and which layers it **must not depend on**. Format rules: `process/registers/layer-dependencies.md`.

The layout and rules below are fixed by ADR-0001 (stack and layering) and ADR-0002 (persistence).
`backend/app/auth/**` has no layer row until ADR-0003 fixes what it may depend on.

| Layer | Path (glob) | Referenced as | Must not depend on | Why |
|---|---|---|---|---|
| `domain` | `backend/app/domain/**` | `app.domain` | services, data, api, integrations | ADR-0001: the domain knows no storage, transport or external system |
| `services` | `backend/app/services/**` | `app.services` | api | ADR-0001: use cases don't know HTTP |
| `data` | `backend/app/data/**` | `app.data` | services, api, integrations | ADR-0001, ADR-0002: persistence is called, it doesn't call in |
| `integrations` | `backend/app/integrations/**` | `app.integrations` | services, data, api | ADR-0001: adapters are called, they don't call in; Google specifics pending ADR-0006 |
| `core` | `backend/app/core/**` | `app.core` | domain, services, data, api, integrations | ADR-0001: configuration is read by every layer and reads none |
| `api` | `backend/app/api/**` | `app.api` | — | ADR-0001: the outermost backend layer |
| `fe-api` | `frontend/src/api/**` | `@/api` | fe-components, fe-features | ADR-0001: the typed client knows no UI |
| `fe-components` | `frontend/src/components/**` | `@/components` | fe-api, fe-features | ADR-0001: presentational components don't fetch |
| `fe-features` | `frontend/src/features/**` | `@/features` | — | ADR-0001: screens compose the client and the components |
