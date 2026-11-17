from dataclasses import dataclass
from typing import List, Optional


class DuplicateEmailError(ValueError):
    """Raised when an email address is already registered."""


@dataclass
class User:
    id: int
    email: str
    password: str
    is_admin: bool = False


@dataclass
class Project:
    id: int
    name: str
    header: List[str]


@dataclass
class Record:
    """One CSV row, as one particular revisor sees it."""
    id: int
    project_id: int
    position: int
    original_values: List[str]
    revised_values: Optional[List[str]] = None   # None = this revisor has not saved it yet
    revised_at: Optional[str] = None             # UTC "YYYY-MM-DD HH:MM:SS"

    @property
    def values(self) -> List[str]:
        return self.revised_values if self.revised_values is not None else self.original_values


@dataclass
class Revision:
    """A revisor's saved version of one record (used for export)."""
    record_id: int
    user_id: int
    email: str
    values: List[str]
    revised_at: str


@dataclass
class PageReview:
    project_id: int
    page: int
    user_id: int
    revised_at: str


@dataclass
class Change:
    id: int
    record_id: int
    col: str
    old_value: str
    new_value: str
    user_id: int
    changed_at: str
    email: Optional[str] = None
    position: Optional[int] = None
    project_name: Optional[str] = None


@dataclass
class SaveResult:
    page: int
    pages: int
    cells_changed: int
    records_changed: int


@dataclass
class RevisorProjectProgress:
    """One revisor's progress in one project."""
    project_id: int
    project_name: str
    total_records: int
    pages: int
    pages_done: int
    records_revised: int
    pct: int
    next_page: int          # first page not yet marked done (last page if all done)


@dataclass
class RevisorProgressRow:
    """One row of the admin progress report."""
    user_id: int
    email: str
    pages_done: int
    pct: int
    records_revised: int
    last_activity: Optional[str]


@dataclass
class ProjectProgressReport:
    project_id: int
    project_name: str
    total_records: int
    pages: int
    rows: List[RevisorProgressRow]
