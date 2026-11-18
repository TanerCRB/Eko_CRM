"""EKO-3-01 fix round 1, Reviewer R-02 (decision A on Issue #195): every customer request resolves
its session once. The access-first pre-solve and the route's own dependencies both solve
`authenticate`; the decision kept on the request makes the second one reuse the first, so
`Authenticator.authenticate` (which touches, and may refresh, the session) runs once.
"""

from typing import Any

import pytest

from tests.runtime.eko301.conftest import CUSTOMERS, REP_A, Crm, created_id, customer_url

pytestmark = pytest.mark.runtime


@pytest.fixture
def counted(crm: Crm, monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    calls: list[str | None] = []
    auth = crm.app.state.auth
    resolve = auth.authenticate

    def counting(cookie: str | None) -> Any:
        calls.append(cookie)
        return resolve(cookie)

    monkeypatch.setattr(auth, "authenticate", counting)
    return calls


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("POST", CUSTOMERS, {"name": "Gospodarstwo Raz"}, id="create"),
        pytest.param("GET", CUSTOMERS, None, id="list"),
        pytest.param("GET", "read", None, id="read"),
        pytest.param("POST", CUSTOMERS, {"name": ""}, id="create-rejected"),
    ],
)
def test_r02_the_session_is_resolved_once_per_customer_request(
    crm: Crm, counted: list[str | None], method: str, path: str, body: Any
) -> None:
    rep = crm.login(REP_A, ["rep"])
    if path == "read":
        path = customer_url(created_id(rep, {"name": "Gospodarstwo Do Odczytu"}))
    counted.clear()
    kwargs = {} if body is None else {"json": body}
    response = rep.send(method, path, **kwargs)
    assert response.status_code < 500, response.text
    assert len(counted) == 1, counted
