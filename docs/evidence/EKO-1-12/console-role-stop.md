# EKO-1-12 console-role stop record

Date: 2026-11-04
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba

## Stop result

The ADR-0003 console-role stop fired against the real local composition. The account held only the exact application `administrator` composite. It could authenticate and create, disable, enable, and set a password on a synthetic account. It then received an empty client list for `eko-backend`, first with `clientId=eko-backend` and again with `search=true`, so it could not resolve the client UUID needed to assign application client roles.

Commands:

- `uv run pytest -m runtime tests/runtime/test_eko112_k03_runtime_roles_and_events.py::test_k03_administrator_operations_denials_and_stored_admin_events --tb=native -q`
- Plain `clientId` query: failed with `expected one client eko-backend`, `len(clients) == 0`.
- `search=true` query: failed with the same empty result.

No role was added to make the operation pass. In particular, `view-clients`, `realm-admin`, `impersonation`, `manage-realm`, and `manage-clients` were not added. The required ADR-0003 addendum is returned to the human before any expanded role set is considered.

K-03 is therefore STOPPED, not a pass. K-04 and K-05 were not run after this mandatory stop; reset timing, unknown-username privacy, and their human decisions remain unchecked.
