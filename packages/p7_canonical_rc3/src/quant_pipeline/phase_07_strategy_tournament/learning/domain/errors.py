from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...errors import P7Error, P7ErrorContext

@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    message: str
    field: str | None = None
    candidate_id: str | None = None
    query_id: str | None = None
    details: dict[str, Any] | None = None

class P7LearningError(P7Error):
    """Structured fatal error shared by P7.S5 and P7.S6."""
    def __init__(self, issue: Issue) -> None:
        super().__init__(
            issue.code, issue.message,
            P7ErrorContext(field=issue.field, candidate_ids=(issue.candidate_id,) if issue.candidate_id else (), details=issue.details),
        )
        self.issue = issue

# Backward-compatible public aliases. They intentionally refer to one class.
P7S5Error = P7LearningError
P7S6Error = P7LearningError

def fail(
    code: str,
    message: str,
    *,
    field: str | None = None,
    candidate_id: str | None = None,
    query_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    raise P7LearningError(
        Issue(
            code=code,
            message=message,
            field=field,
            candidate_id=candidate_id,
            query_id=query_id,
            details=details,
        )
    )
