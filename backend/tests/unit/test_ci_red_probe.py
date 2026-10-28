"""Deliberately failing test: shows the backend CI job turns a PR red (EKO-1-06, K-05). Never merged."""


def test_ci_red_probe_fails_on_purpose() -> None:
    assert 1 == 2, "deliberate failure for the K-05 red-run evidence"
