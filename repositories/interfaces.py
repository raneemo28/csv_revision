from abc import ABC, abstractmethod
from typing import List, Optional, Set

from models import (
    User, Project, Record, Revision, PageReview, Change,
    RevisorProjectProgress,
)


class UnitOfWork(ABC):
    """Repositories never commit; the service layer commits once per operation."""

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]: ...

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    def create(self, email: str, password_hash: str, is_admin: bool = False) -> User: ...

    @abstractmethod
    def get_all(self) -> List[User]: ...

    @abstractmethod
    def get_revisors(self) -> List[User]: ...


class ProjectRepository(ABC):
    @abstractmethod
    def get_by_id(self, project_id: int) -> Optional[Project]: ...

    @abstractmethod
    def get_all(self) -> List[Project]: ...

    @abstractmethod
    def create(self, name: str, header: List[str]) -> Project: ...


class RecordRepository(ABC):
    @abstractmethod
    def get_page(self, project_id: int, user_id: int, limit: int, offset: int) -> List[Record]:
        """Records of a project as seen by one revisor (their saved values, if any)."""

    @abstractmethod
    def get_all_by_project(self, project_id: int) -> List[Record]:
        """All records with original values only, ordered by position."""

    @abstractmethod
    def count_by_project(self, project_id: int) -> int: ...

    @abstractmethod
    def create_batch(self, project_id: int, rows: List[List[str]]) -> None: ...


class RevisionRepository(ABC):
    @abstractmethod
    def save(self, record_id: int, user_id: int, values: List[str], at: str) -> None: ...

    @abstractmethod
    def get_by_project(self, project_id: int) -> List[Revision]: ...


class PageReviewRepository(ABC):
    @abstractmethod
    def get(self, project_id: int, page: int, user_id: int) -> Optional[PageReview]: ...

    @abstractmethod
    def get_done_pages(self, project_id: int, user_id: int) -> Set[int]: ...

    @abstractmethod
    def set(self, project_id: int, page: int, user_id: int, at: str) -> None: ...

    @abstractmethod
    def delete(self, project_id: int, page: int, user_id: int) -> None: ...


class ChangeRepository(ABC):
    @abstractmethod
    def create(self, record_id: int, col: str, old_value: str, new_value: str,
               user_id: int, at: str) -> None: ...

    @abstractmethod
    def get_recent(self, project_id: Optional[int] = None, limit: int = 500) -> List[Change]: ...


class ProgressRepository(ABC):
    @abstractmethod
    def revisor_progress(self, user_id: int, page_size: int) -> List[RevisorProjectProgress]: ...

    @abstractmethod
    def project_totals(self, page_size: int) -> List[dict]:
        """[{project_id, project_name, total_records, pages}] newest project first."""

    @abstractmethod
    def revisor_rows(self, page_size: int) -> List[dict]:
        """One dict per (project, revisor) pair, including revisors who have not started."""
