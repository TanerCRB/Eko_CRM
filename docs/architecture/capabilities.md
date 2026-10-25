# Capability register

Answers one question only: **what can the system actually do, and what proves it.** Architectural
decisions say what was agreed; this register says what exists. Format and allowed evidence values:
`process/registers/capability-register.md` — `mutation-tested`, `test`, `manual <YYYY-MM-DD>`,
`none`, nothing else.

| Capability | Evidence | Where | What this does not prove |
|---|---|---|---|
| — (no code yet) | none | — | — |

## Mutations

One row per mutation QA ran. A survived mutation stays in the table with how the test was fixed.

| Task | Removed mechanism | Result | Patch |
|---|---|---|---|
| EKO-1-03 | ADR-0004 round-1 set (K-01..K-07): runtime, composition, migrate process, exposure, secrets, backup, restore, forwarded items, operator duties, change-set boundary (M01–M58) | killed — 1–39 checks each; text only; M48 and M56 survived the first script version and were killed after the check was fixed | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 fix-round-1 set (K-01..K-06): revision check, rollback, re-apply and session key, listeners, verification, approver (M59–M107) | killed — 1–6 checks each; text only; each survived the round-0 script | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 migrate on every start with no exception, no-op on a descending revision, failure on an unplaceable one, rollback running migrate (K-01; M67, M106, M108, M126–M132, M157) | killed — 1–2 checks each; the fix-round-1 script passed a skip sentence naming the rolled-back release (M108) | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 one-release rollback as a procedural rule; an access-rule release not rollbackable (K-01; M133–M136) | killed — 1 check each; text only | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 restore: public listener company-network only until the last step, test login through it, Keycloak-stored secrets from master copies, rotations recorded and re-applied (K-04; M113, M115–M125) | killed — 1–2 checks each; the fix-round-1 script passed "Start keycloak and proxy with both of its listeners" (M113); runtime proof C18/C25 in EKO-1-08 | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 monthly verification against the off-server record, last three verified sets, restore-host requirements (K-04; M112, M145–M154) | killed — 1–2 checks each; the fix-round-1 script passed "may be skipped after the first year" (M112) | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 backup role connection limit covering its concurrent sessions (K-04; M140, M141) | killed — 1 check each; runtime proof C19 in EKO-1-06 | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 bootstrap from inside the keycloak container before proxy starts (K-06; M137–M139) | killed — 1 check each | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 approver entering the approval; no assignment before it (K-06; M114, M142–M144) | killed — 1 check each; the fix-round-1 script passed "assign first and enter the approval afterwards" (M114) | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
| EKO-1-03 | ADR-0004 admin listener published anywhere else, WAN interface next to `<auth-admin-host>` (K-02; M110, M156, M155 regression) | killed — M110 passed the fix-round-1 script; M156 survived QA's second version (`\b` next to `<` never matches) and was killed after the check was fixed | [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) comments, Base `d21c448` |
