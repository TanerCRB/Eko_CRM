"""Stand-ins for the release record in GHCR and for reachability from `main` (EKO-1-15).

The record double holds release compositions by tag, as the OCI artifact repository does; a tag
it does not hold has no release composition. Reachability is a set of commits on `main`.
"""

from dataclasses import dataclass, field

from tests.support.releases import CannotTell, Release

MAIN = "a" * 40
MAIN_OLDER = "b" * 40
BRANCH = "c" * 40


@dataclass
class RecordDouble:
    releases: dict[str, Release] = field(default_factory=dict)
    refuse_listing: bool = False
    missing: set[str] = field(default_factory=set)

    def tags(self) -> list[str]:
        if self.refuse_listing:
            raise CannotTell("the record listing was refused")
        return list(self.releases)

    def release(self, tag: str) -> Release:
        if tag in self.missing or tag not in self.releases:
            raise CannotTell(f"{tag}: release composition cannot be obtained")
        return self.releases[tag]


@dataclass
class ReachDouble:
    on_main: set[str] = field(default_factory=lambda: {MAIN, MAIN_OLDER})
    unknown: set[str] = field(default_factory=set)

    def reachable(self, commit: str) -> bool:
        if commit in self.unknown:
            raise CannotTell(f"{commit}: reachability from main cannot be determined")
        return commit in self.on_main


def backend_ref(tag: str) -> str:
    return f"ghcr.io/tanercrb/eko-crm/backend:{tag}@sha256:" + tag.encode().hex().ljust(64, "0")


def release(tag: str, commit: str = MAIN_OLDER) -> Release:
    composition = f"services:\n  backend:\n    image: {backend_ref(tag)}\n"
    return Release(tag=tag, commit=commit, composition=composition)


def record(*tags: str, commit: str = MAIN_OLDER) -> RecordDouble:
    return RecordDouble({tag: release(tag, commit) for tag in tags})
