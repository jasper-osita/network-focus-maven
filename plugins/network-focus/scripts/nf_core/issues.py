from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["block", "warn", "info"]


@dataclass
class Issue:
    """A data problem found by code. `message` is plain English for the chief of staff."""
    code: str
    severity: Severity
    message: str
    rows: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class BlockingError(Exception):
    """Raised when the run cannot continue. Carries a block-level Issue."""

    def __init__(self, issue: Issue):
        super().__init__(issue.message)
        self.issue = issue


def block(code: str, message: str) -> BlockingError:
    return BlockingError(Issue(code, "block", message))
