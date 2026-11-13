"""EKO-1-26 QA (K-01): the guard's Keycloak halves, planted statically.

`test_eko119_k04_session_images.py` keeps the four-family incidents and its EXCEPTIONS equality
pin, and this task's DoD 4 holds that file byte-identical; route A makes the custom Keycloak
image the fifth member of the family, so its pass case (the placed checked name is never read
as a session build) and its fail case (the in-session compose build of the anchor — the exact
reference of run 42954811816 — is flagged and named by the violation line) get their own
carrier here. The whitelist cheat for this reference is blocked by the equality pin in the
other file; the live halves of both are QA's release-mode session at this head.
"""

from tests.support import session_images as si

COMPOSE_LABEL = {"com.docker.compose.project": "ekort-fresh-31db3650"}
CHECKED: dict[str, dict[str, str]] = {
    f"eko-crm/{name}:checked": {} for name in ("backend", "frontend", "proxy", "backup", "keycloak")
}
KEYCLOAK_ANCHOR = "localhost/eko-crm/keycloak:26.8.1-eko112"


def test_eko126_qa_k01_the_placed_keycloak_name_is_never_a_session_build() -> None:
    # The session consumes the name the placing step put there before the snapshot; postgres and
    # mailpit are pulled third parties without Compose's label — nothing here is this session's.
    after = {
        **CHECKED,
        "postgres:18.6-trixie": {},
        "axllent/mailpit:v1.32.0": {},
    }
    assert si.violations(set(CHECKED), after) == []


def test_eko126_qa_k01_the_session_built_keycloak_anchor_is_flagged_and_named() -> None:
    found = si.violations(set(CHECKED), {**CHECKED, KEYCLOAK_ANCHOR: COMPOSE_LABEL})
    assert found == [f"{KEYCLOAK_ANCHOR}: built by Compose for project ekort-fresh-31db3650"], found
