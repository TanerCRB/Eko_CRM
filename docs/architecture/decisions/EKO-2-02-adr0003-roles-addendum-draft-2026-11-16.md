# EKO-2-02 — Role-free logout and CRM-data refusal by default — ADR-0003 addendum draft — 2026-11-16

**Status:** Accepted 2026-11-16 (human, gate 1 of EKO-2-02 fix round 1, Issue #22; chosen in-session and recorded by the driving session on the human's instruction: the addendum, the closed role-free and non-CRM lists in `backend/app/main.py`, and the amended criteria under fingerprint c64ee9e17ef70c71056273da8dae0aad495e4a98). The "Addendum text" is appended to ADR-0003 as a dated addendum in this task's gate-3 documentation PR.
<!-- Only a human changes this status. The section "Addendum text" is appended to ADR-0003 as a
dated addendum (date = human acceptance) in this task's gate-3 documentation PR. This file is never
itself appended to or edited inside ADR-0003's accepted text. -->

## Context

EKO-2-02 (Issue #22) was implemented and verified at `1044cde`. Two findings from verification
went back to the human. On 2026-11-16 the human decided both, as recorded on the Issue and in the
task journal: "R-01 fix in gate (default-deny admin-only, non-CRM marked routes); B-01 fix here ->
ADR-0003 addendum + criteria amendment -> back to gate 1".

**R-01 (Reviewer, medium).** ADR-0003 *Roles* says: "An account holding only `administrator` is
denied every API operation that reads or changes customers, visits, notes, actions or dashboards
(HTTP 403)." In the verified code, the application-wide dependency `authenticate`
(`backend/app/auth/gate.py:38-48`) refuses only a caller with no application role. The
administrator exclusion lives in `crm_data_caller` (`gate.py:57-60`), and a route gets it only if
its author declares it. A CRM route that declares only `current_caller`, or declares nothing,
would serve CRM data to an administrator-only account. QA's contrast
`backend/tests/runtime/test_eko202_qa_contrasts.py:55-65` pins exactly that: `["administrator"]`
gets 200 on a route that declares no dependency. The accepted text states the rule but not where it
is enforced. Under the human's decision, the exclusion must be the default of the one
application-wide dependency, not something each route opts into.

**B-01 (Security Auditor, low).** ADR-0003 *Roles* says: "An authenticated account with none of
the three roles is denied every API operation (HTTP 403)." ADR-0003-C5 restates that as "403 on
each route". At gate 1 of EKO-2-02 the human accepted OQ-1 A: the role check covers every route
except the three session-exempt routes (login start, login callback, health), with no ADR
addendum. `POST /api/auth/logout` is therefore refused to a role-less caller before
`Authenticator.logout` runs. The application session and the Keycloak SSO session then survive
until the 30-minute idle limit (ADR-0003 addendum of 2026-11-02, G-1 A). If an administrator grants
a role during that time, the session picks it up at its next refresh, in whatever browser holds the
cookie. The human decided that logout must be able to end a session that holds no application
role. That departs from the letter of *Roles*, of ADR-0003-C5 and of OQ-1 A, so this is a declared
deviation, and the task returns to gate 1.

Constraints this draft keeps:

- ADR-0001 Constraint 2 says identity and roles are "verified on every request by one
  application-wide FastAPI dependency (wired in `backend/app/main.py`, implemented under
  `backend/app/auth/`)". Both rules below live in that dependency. No second gate is added, and no
  route bypasses verification.
- ADR-0003 addendum of 2026-10-28: "Exactly three routes are served without a session ... Adding a
  route to this list is a change to this decision." ADR-0003 addendum of 2026-11-02: "Logout is an
  authenticated operation ... logout is not added to that list." Logout stays session-bound. A
  role-less caller is still an authenticated caller.
- `docs/architecture/layer-dependencies.md`, row `auth`: it must not depend on `services`, `api`
  or `integrations`. The gate cannot import route definitions from `api`. Only `main.py` and
  `api` depend on `auth`.
- Gate-1 OQ-3 A: the test probe route is injected by the test process onto `create_app()`'s output
  only. It is never registered in product code, never exempted, and never gated by a settings flag.

## Decision (proposed)

### 1. Operations a role-less but authenticated caller may still reach

**Exactly one operation: `POST /api/auth/logout`.** Every other operation outside the three
session-exempt routes answers 403 to a role-less caller. That includes `GET /api/auth/session`.

The session read is deliberately left out:

- **The B-01 risk is that a session cannot be ended.** Logout alone removes it. Reading the
  session ends nothing.
- **The 403 already tells the SPA what it needs.** The SPA can distinguish "no session" (401)
  from "authenticated but not permitted" (403), so it can offer logout without first reading the
  subject and name.
- **Answering 200 would mislabel the caller.** The SPA's `SessionGate` treats a 200 on the session
  read as `authenticated` and renders the application shell. That would describe a role-less
  account as a working one.
- **The session read will grow.** Whatever it later returns would become reachable to role-less
  callers by default.

**Consequence for the browser.** Today the SPA shows the "invalid" screen on a 403 from the session
read (`frontend/src/features/session/SessionGate.tsx:54-55,100-105`). That screen has a retry
button and no logout button. The logout button sits in `AccountPanel`, which renders only for an
authenticated phase. So with this rule alone, B-01 is closed at the API but not yet in the
browser. Gate-1 question Q-1 below asks the human where the frontend half goes.

### 2. Default refusal of administrator-only callers (R-01)

- **Default.** For every operation that is not session-exempt, the application-wide dependency
  refuses (403) a caller whose roles do not include `rep` or `manager`, unless the operation is
  marked **non-CRM**. This covers callers holding only `administrator`. "Non-CRM" means the
  operation reads or changes none of customers, visits, notes, actions or dashboards, and returns
  no data derived from them. Every operation without the mark is CRM-data class. That includes
  every operation added later, any route a test injects, and a route that declares no dependency
  of its own.
- **The non-CRM operations at this addendum's date:** `GET /api/auth/session` and
  `POST /api/auth/logout`.
- **Who may mark an operation non-CRM.** Only the human, at gate 1 of the task that adds or
  changes the operation. The Architect's impact map for that task must name the operation (method
  and path) and state why it is non-CRM in the sense above. The mark needs no ADR addendum of its
  own. The human's gate-1 record and the capability register row raised at gate 3 carry it.
  Neither a Developer nor an evaluating role adds a mark on its own authority.
- **How the mark is expressed.** Each list is one closed constant in `backend/app/main.py`, beside
  `PUBLIC_PATHS`:
  - the role-free list, holding exactly the operation of section 1;
  - the non-CRM list.

  Each entry is a (method, path) pair as served. When `create_app()` builds the application, it
  resolves every entry to its served route object, as `_public_routes` does today. The build fails
  in any of these cases:
  - an entry is not served;
  - an entry's path is in `PUBLIC_PATHS`;
  - a role-free entry is missing from the non-CRM list.

  The gate compares the matched route object by identity. It does not compare path strings or
  prefixes, and it reads no route-level attribute or dependency that an author in `api` could set.
  A test reads both constants directly and compares them with lists it holds itself, as
  `test_k06_exemption_list_is_exactly_the_three_routes` already does for `PUBLIC_PATHS`. No
  settings value, environment variable or request input can add to either list (ADR-0001
  Constraint 1; gate-1 OQ-3 A).
- **Relation to the session-exempt list.** There are three disjoint classes, checked in this order
  after the unchanged `Origin` check:
  1. **Session-exempt.** Exactly the three routes of the addendum of 2026-10-28, served without a
     session and never reached by any role check. The list stays exactly three. Neither logout
     nor any non-CRM operation joins it.
  2. **Role-free.** Exactly `POST /api/auth/logout`. It requires a session resolved and verified
     as *How a request is verified* says: 401 without one, and 503 while Keycloak is unreachable
     on renewal. It requires no application role.
  3. **Non-CRM.** It requires a session and at least one application role, and it admits a
     caller holding only `administrator`.

  Everything else is CRM-data class. It requires a session and `rep` or `manager`. Rights inside
  that class (for example `manager_caller`) and per-record ownership (ACC-4/ACC-5) stay with each
  route and its feature task.
- **The rule is per token, unchanged.** The union rule of *Roles* stands: `manager` plus
  `administrator` has manager rights. A role removed in Keycloak takes effect within the
  5-minute bound, now including the change from CRM-data access to refusal.

### 3. Effect on ADR-0003-C5's letter and on gate-1 OQ-1 A

- *Roles*, bullet "An authenticated account with none of the three roles is denied every API
  operation": from acceptance, every API operation **except logout**. This is the deviation.
- *Roles*, bullet "`administrator` grants no CRM data": unchanged in substance. It is now enforced
  as a default (section 2). Enforcing it this way is stricter than the letter, which named only
  the five CRM data kinds, and is not a deviation.
- ADR-0003-C5 is restated (see *Addendum text*). The three session-exempt routes now appear in
  C5's own text, as they already do in C4's since 2026-10-28.
- Gate-1 **OQ-1 A** ("the role check cannot reach the three session-exempt routes; no ADR
  addendum") is superseded on acceptance. Its reading of the exempt routes is kept and becomes
  text. Its scope, "the role check covers every route except the three", becomes "every route
  except the three, and logout for the no-role refusal only". Its "no addendum" choice is replaced
  by this addendum.
- Gate-1 **OQ-3 A** is unchanged and gains one consequence: the probe route is never in either new
  list. Its CRM-data class comes from carrying no mark, not from declaring `crm_data_caller`.
- The Issue's *Out of scope* line "Logout usability for a role-less or disabled account" no longer
  holds for role-less accounts at the API. Whether it stays for the SPA half is Q-1.

## Options considered

### Which operations a role-less caller may reach (B-01)

| Option | Cost | Closes off |
|---|---|---|
| **A. Logout only** (recommended) | A one-operation deviation from *Roles* and C5. The SPA needs a logout action on its 403 screen before a browser user can use it (Q-1). | Nothing. A later need for a role-free read is a new addendum. |
| B. Logout and the session read | A two-operation deviation. The SPA shows the full shell to a role-less account, and every later field of the session read reaches role-less callers. B-01 closes in the browser without a frontend change, through `AccountPanel`. | Using the session read's 403 as the "authenticated, no role" signal. |
| C. No change; accept B-01 as residual risk | None now. A role-less session cannot be ended for up to 30 minutes and picks up a role granted in that window. | The human's decision of 2026-11-16 rejected this. |

### Where the administrator exclusion is enforced (R-01)

| Option | Cost | Closes off |
|---|---|---|
| **A. Default refusal in the application-wide dependency; non-CRM operations marked** (the human's decision of 2026-11-16) | QA's administrator → 200 pin and K-01's administrator walk change. Every future non-CRM operation needs a gate-1 mark. | A CRM route serving administrator-only callers because its author forgot a dependency. |
| B. Opt-in per route (`crm_data_caller`), with a route-table walk failing on an unmarked route that serves administrator | Detection after the fact, in tests only, while production code keeps fail-open behavior. | Nothing structurally. R-01 can recur wherever the walk does not reach. |
| C. Opt-in per route, plus an administrator-only 403 contrast required in each feature task's criteria | Relies on every feature task's Analyst and QA. | Same as B. |

### How the non-CRM mark is expressed

| Option | Cost | Closes off |
|---|---|---|
| **A. Closed (method, path) constants in `main.py`, resolved to route objects at build, compared by identity** (recommended) | A non-CRM route is changed in two places: its handler in `api/` and the list in `main.py`. `main.py` is an architecture-sensitive path, so every mark is visible to the risk check and review. | Marking a route from inside `api/` alone. |
| B. A route-level marker: a dependency or route attribute defined in `auth`, read by the gate from the matched route | Kept next to the route. Any `api` author can opt out with one token in any file. A check has to walk every route to find the marks. | A single, closed list a test can compare. |
| C. A registry in `auth` | `auth` would have to name `api` paths. That does not violate the layer table, but it puts product route knowledge in an inner layer. | Keeping route knowledge in `main.py` and `api`. |

### Who may mark an operation non-CRM

| Option | Cost | Closes off |
|---|---|---|
| **A. The human at gate 1 of the task, on the Architect's named justification** (recommended) | One gate-1 item per non-CRM operation. | A mark added during implementation or review. |
| B. An ADR-0003 addendum per mark, like the session-exempt list | An accepted-text change for each non-CRM route. | Same as A, with more cost. Better kept for the role-free list, which can leak an unauthorised session's actions. |
| C. The Developer, checked by Reviewer and Guardian | No gate cost. | The human's control over which operations an administrator reaches. R-01 recurs as a review-quality question. |

## Recommendation

Accept B-01 **A**, R-01 **A**, mark expression **A** and mark authority **A**:

- **Smallest deviation.** Only logout changes the no-role rule, and only to end a session, never
  to read one.
- **Fails closed.** Every new route is CRM-data class until a human says otherwise, which is the
  direction ADR-0003 *Roles* already promises.
- **One closed list, one place.** The marks sit in `main.py` beside the existing exemption list,
  so one test comparison holds them. The gate stays in `auth` without importing `api`
  (`layer-dependencies.md`, row `auth`).
- **The session-exempt list keeps its three routes.** ADR-0001 Constraint 2 (one application-wide
  dependency) and the addendum of 2026-11-02 ("logout is an authenticated operation", "not added
  to that list") are satisfied as written.

## Addendum text

The following is the text proposed for ADR-0003 as a dated addendum, appended in the gate-3
documentation PR of EKO-2-02.

> ### <acceptance date> — Logout without an application role; CRM-data refusal by default
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-2-02, Issue #22).
>
> **What it changes.** *Roles* denies every API operation to an authenticated account with none of
> the three roles, logout included. Such a session therefore cannot be ended by its user. It lives
> until the idle limit and gains any role granted in that window at its next refresh. *Roles*
> also denies an administrator-only account every operation on customers, visits, notes, actions
> or dashboards, but does not say where that is enforced. From this date:
>
> - **Logout needs no application role.** `POST /api/auth/logout` is the only API operation an
>   authenticated account with none of `rep`, `manager`, `administrator` may call. It still
>   requires a session resolved and verified as *How a request is verified* says, the `Origin`
>   rule of *Browser flow* and the termination rules of the addendum of 2026-11-02. Every other
>   operation outside the three session-exempt routes answers 403 to such an account, the session
>   read included. Adding an operation to this role-free list is a change to this decision,
>   recorded as an addendum.
> - **CRM-data refusal is the default.** The application-wide access dependency refuses (403)
>   every operation outside the session-exempt routes to a caller holding neither `rep` nor
>   `manager`, unless the operation is marked non-CRM. A non-CRM operation reads or changes none
>   of customers, visits, notes, actions or dashboards and returns no data derived from them.
>   An operation without the mark is CRM-data class, whether it is added later, injected by a
>   test, or declares no dependency of its own. At this date the non-CRM operations are
>   `GET /api/auth/session` and `POST /api/auth/logout`.
> - **Who marks, and how.** An operation is marked non-CRM only by the human at gate 1 of the task
>   that adds or changes it, on the Architect's impact map, which names the operation and why it
>   is non-CRM. The role-free list and the non-CRM list are each one closed constant of (method,
>   path) entries in `backend/app/main.py`, beside the session-exempt list. Building the
>   application fails when an entry is not served, when an entry's path is session-exempt, or when
>   the role-free entry is not also non-CRM. The dependency matches the served route object by
>   identity. No route attribute, setting, environment value or request input adds to either list.
> - **Three classes, disjoint.** The session-exempt list holds exactly the three routes of the
>   addendum of 2026-10-28, and neither logout nor any non-CRM operation joins it. The role-free
>   list holds exactly logout. The non-CRM list holds the operations marked as above.
> - **ADR-0003-C5 reads:** A test walking every API operation other than the start of a login,
>   the login callback and the health route (this exemption list is held in the test explicitly)
>   makes these checks:
>   - with a verified token holding none of `rep`, `manager`, `administrator` (including one
>     holding realm roles with those names), every operation answers 403 except logout, which ends
>     the session;
>   - with only `administrator`, every operation outside the non-CRM list held in the test answers
>     403, including an operation planted by the test that declares no dependency of its own;
>   - with `manager` and `administrator`, every operation answers as with `manager` alone;
>   - the role-free list and the non-CRM list in the application equal the lists held in the test,
>     and neither shares a path with the session-exempt list.
>
> Every other rule and control of this decision is unchanged. In particular, the session-exempt
> list holds exactly three routes, ADR-0003-C4 and C23 are unchanged, and logout is not served
> without a session.
>
> **Why.** A session that its user cannot end, and that silently gains a role granted later, is a
> security effect, not a usability gap (EKO-2-02 Security Auditor finding B-01). Ending a session
> grants no data, so it is the one operation exempted from the no-role refusal. An exclusion that
> each route must remember fails open on the first route that forgets it (EKO-2-02 Reviewer
> finding R-01). Making refusal the default means the next CRM route is refused, not served.
> Restating ADR-0003-C5 and the *Roles* no-role bullet is a declared deviation. It follows the
> precedent of this decision's addendum of 2026-10-28 on ADR-0003-C4. It supersedes gate-1
> decision OQ-1 A of EKO-2-02 (2026-11-06), whose exemption reading it keeps as text. Approved by
> the human at gate 1 of EKO-2-02 on <acceptance date> (Issue #22).

## Controls

No new control identifier. ADR-0003-C5 is restated above. C4, C6, C7, C23 and C25 are unchanged
and continue to bind. C25's logout proof runs with role-holding fixture accounts. The role-less
logout case is carried by the restated C5.

## Open questions for gate 1

- **Q-1, where the SPA half of B-01 goes.** (A, recommended) This task stays backend-only, and a
  linked follow-up Issue gives the SPA's 403 session screen a logout action. Until that lands, the
  capability row and *Out of scope* say plainly that the browser offers no logout to a role-less
  account. (B) Widen EKO-2-02 to include the frontend change, which brings in
  `developer-frontend`, new criteria and frontend QA. (C) Take option B of the role-free table
  (logout plus the session read), which closes the browser path with no frontend change at the
  cost of a two-operation deviation.
- **Q-2, accept this addendum text as the ADR-0003 addendum** (A, recommended), or reject it
  (B). If rejected, B-01 remains an accepted residual risk under the existing *Out of scope* line,
  widened to name the security effect, and R-01 needs another resolution.
- **Q-3, mark authority:** confirm option A (human at gate 1) over B (an addendum per mark) or C
  (Developer plus review).
