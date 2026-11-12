from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    """The authenticated staff member passed inward from the access dependency (ADR-0003 *Roles*).

    `subject` is the identity server's `sub`, compared exactly. Roles join this value with EKO-2-02.
    """

    subject: str
    name: str | None
