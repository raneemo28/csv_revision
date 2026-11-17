from abc import ABC, abstractmethod
from typing import List, Optional, Set, Tuple

from models import (
    User, Project, Record, Change, SaveResult,
    RevisorProjectProgress, ProjectProgressReport,
)


class AuthService(ABC):
    @abstractmethod
    def register(self, email: str, password: str) -> User:
        """Create a revisor account."""

    @abstractmethod
    def login(self, email: str, password: str) -> Optional[User]: ...

    @abstractmethod
    def get_user(self, user_id: int) -> Optional[User]: ...


class ProjectService(ABC):
    @abstractmethod
    def create_project(self, name: str, header: List[str], rows: List[List[str]]) -> Project: ...

    @abstractmethod
    def get_project(self, project_id: int) -> Optional[Project]: ...

    @abstractmethod
    def list_projects(self) -> List[Project]: ...

    @abstractmethod
    def export_project(self, project_id: int) -> Tuple[List[str], List[List[str]]]: ...


class RecordService(ABC):
    @abstractmethod
    def get_page(self, project_id: int, page: int, page_size: int,
                 revisor_id: int) -> Tuple[List[Record], int, int]: ...

    @abstractmethod
    def save_page(self, project_id: int, page: int, page_size: int, revisor_id: int,
                  form_data, header: List[str], mark_done: bool) -> SaveResult: ...

    @abstractmethod
    def get_done_pages(self, project_id: int, revisor_id: int) -> Set[int]: ...


class ProgressService(ABC):
    @abstractmethod
    def for_revisor(self, revisor_id: int) -> List[RevisorProjectProgress]: ...

    @abstractmethod
    def for_admin(self) -> List[ProjectProgressReport]: ...


class AdminService(ABC):
    @abstractmethod
    def get_changes(self, project_id: Optional[int] = None) -> List[Change]: ...
