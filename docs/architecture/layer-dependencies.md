# Layer dependencies

The task command reads this file through `scripts/layer-check.sh` (`.claude/commands/task.md`,
step 10a, "Layer check"). Each row names one layer: where its files live, how other code refers to
it, and which layers it **must not depend on**. Format rules: `process/registers/layer-dependencies.md`.

The layout and rules below are fixed by ADR-0001 (stack and layering), ADR-0002 (persistence) and
ADR-0003 (identity and access; the `auth` rule in the inner rows is ADR-0001's addendum of
2026-10-23).

| Layer | Path (glob) | Referenced as | Must not depend on | Why |
|---|---|---|---|---|
| `domain` | `backend/app/domain/**` | `app.domain` | services, data, api, integrations, auth | ADR-0001: the domain knows no storage, transport or external system; ADR-0003: only api and main.py depend on auth |
| `services` | `backend/app/services/**` | `app.services` | api, auth | ADR-0001: use cases don't know HTTP; ADR-0003: only api and main.py depend on auth |
| `data` | `backend/app/data/**` | `app.data` | services, api, integrations, auth | ADR-0001, ADR-0002: persistence is called, it doesn't call in; ADR-0003: only api and main.py depend on auth |
| `integrations` | `backend/app/integrations/**` | `app.integrations` | services, data, api, auth | ADR-0001: adapters are called, they don't call in; Google specifics pending ADR-0006; ADR-0003: only api and main.py depend on auth |
| `core` | `backend/app/core/**` | `app.core` | domain, services, data, api, integrations, auth | ADR-0001: configuration is read by every layer and reads none; ADR-0003: only api and main.py depend on auth |
| `auth` | `backend/app/auth/**` | `app.auth` | services, api, integrations | ADR-0003: verifies the identity server's assertion and the browser session, builds the caller as a domain value; Keycloak is not an integration |
| `api` | `backend/app/api/**` | `app.api` | — | ADR-0001: the outermost backend layer |
| `fe-api` | `frontend/src/api/**` | `@/api` | fe-components, fe-features | ADR-0001: the typed client knows no UI |
| `fe-components` | `frontend/src/components/**` | `@/components` | fe-api, fe-features | ADR-0001: presentational components don't fetch |
| `fe-features` | `frontend/src/features/**` | `@/features` | — | ADR-0001: screens compose the client and the components |
| `fe-time` | `frontend/src/time/**` | `@/time` | fe-api, fe-components, fe-features | ADR-0001: the one Europe/Warsaw date helper is used by every frontend layer and uses none |
