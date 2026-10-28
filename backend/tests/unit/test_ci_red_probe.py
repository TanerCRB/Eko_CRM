"""Deliberately failing test for the EKO-1-06 K-05 red-run evidence; never merged."""


def test_ci_red_probe_fails_on_purpose() -> None:
    assert sum([1, 1]) == 3, "deliberate failure"
