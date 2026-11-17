import re
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    User, Project, Record, Change, SaveResult,
    RevisorProjectProgress, RevisorProgressRow, ProjectProgressReport,
)
from repositories.interfaces import (
    UnitOfWork, UserRepository, ProjectRepository, RecordRepository, RevisionRepository,
    PageReviewRepository, ChangeRepository, ProgressRepository,
)
from services.interfaces import (
    AuthService, ProjectService, RecordService, ProgressService, AdminService,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128
# pbkdf2 works everywhere; werkzeug's default (scrypt) can fail on hosts with low memory limits.
HASH_METHOD = "pbkdf2:sha256"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=HASH_METHOD)


def validate_credentials(email: str, password: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise ValueError(f"Password must be at most {MAX_PASSWORD} characters.")
    return email


def _norm(text: str) -> str:
    """Browsers send textarea line breaks as \\r\\n; keep one style."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


_NUMERIC_LIKE = re.compile(r"^[+-][\d\s().,-]+$")


def csv_safe(value: str) -> str:
    """Stop spreadsheet apps from running revisor-typed text as a formula."""
    if value and (value[0] in "=@\t\r" or (value[0] in "+-" and not _NUMERIC_LIKE.match(value))):
        return "'" + value
    return value


class DefaultAuthService(AuthService):
    def __init__(self, user_repo: UserRepository, uow: UnitOfWork):
        self.user_repo = user_repo
        self.uow = uow

    def register(self, email: str, password: str) -> User:
        email = validate_credentials(email, password)
        try:
            user = self.user_repo.create(email, hash_password(password), is_admin=False)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return user

    def login(self, email: str, password: str) -> Optional[User]:
        user = self.user_repo.get_by_email((email or "").strip().lower())
        if user and check_password_hash(user.password, password or ""):
            return user
        return None

    def get_user(self, user_id: int) -> Optional[User]:
        return self.user_repo.get_by_id(user_id)


class DefaultProjectService(ProjectService):
    def __init__(self, project_repo: ProjectRepository, record_repo: RecordRepository,
                 revision_repo: RevisionRepository, uow: UnitOfWork):
        self.project_repo = project_repo
        self.record_repo = record_repo
        self.revision_repo = revision_repo
        self.uow = uow

    def create_project(self, name: str, header: List[str], rows: List[List[str]]) -> Project:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the project a name.")
        if len(name) > 120:
            raise ValueError("The project name is too long (120 characters maximum).")
        try:
            project = self.project_repo.create(name, header)
            self.record_repo.create_batch(project.id, rows)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return project

    def get_project(self, project_id: int) -> Optional[Project]:
        return self.project_repo.get_by_id(project_id)

    def list_projects(self) -> List[Project]:
        return self.project_repo.get_all()

    def export_project(self, project_id: int) -> Tuple[List[str], List[List[str]]]:
        """Original columns, then for every revisor who saved something in this project:
        [revisor email] [one column per original column with their values] [revised at (UTC)]."""
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        width = len(project.header)

        records = self.record_repo.get_all_by_project(project_id)
        by_user: dict = {}      # email -> {record_id: Revision}
        for rev in self.revision_repo.get_by_project(project_id):
            by_user.setdefault(rev.email, {})[rev.record_id] = rev
        emails = sorted(by_user)

        header = list(project.header)
        for email in emails:
            header.append(csv_safe(f"Revisor email ({email})"))
            header.extend(csv_safe(f"{col} ({email})") for col in project.header)
            header.append(csv_safe(f"Revised at UTC ({email})"))

        rows = []
        for record in records:
            row = list(record.original_values) + [""] * (width - len(record.original_values))
            for email in emails:
                rev = by_user[email].get(record.id)
                if rev is None:
                    row.extend([""] * (width + 2))
                else:
                    values = list(rev.values) + [""] * (width - len(rev.values))
                    row.append(csv_safe(email))
                    row.extend(csv_safe(v) for v in values[:width])
                    row.append(rev.revised_at)
            rows.append(row)
        return header, rows


class DefaultRecordService(RecordService):
    def __init__(self, record_repo: RecordRepository, revision_repo: RevisionRepository,
                 review_repo: PageReviewRepository, change_repo: ChangeRepository,
                 uow: UnitOfWork):
        self.record_repo = record_repo
        self.revision_repo = revision_repo
        self.review_repo = review_repo
        self.change_repo = change_repo
        self.uow = uow

    def get_page(self, project_id: int, page: int, page_size: int,
                 revisor_id: int) -> Tuple[List[Record], int, int]:
        total = self.record_repo.count_by_project(project_id)
        pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, pages))
        records = self.record_repo.get_page(project_id, revisor_id, page_size, (page - 1) * page_size)
        return records, page, pages

    def save_page(self, project_id: int, page: int, page_size: int, revisor_id: int,
                  form_data, header: List[str], mark_done: bool) -> SaveResult:
        records, page, pages = self.get_page(project_id, page, page_size, revisor_id)
        width = len(header)
        now = utc_now()
        cells_changed = 0
        records_changed = 0
        try:
            for record in records:
                current = [_norm(v) for v in record.values] + [""] * (width - len(record.values))
                current = current[:width]
                new = list(current)
                for i in range(width):
                    key = f"c_{record.id}_{i}"
                    if key in form_data:
                        new[i] = _norm(form_data[key])
                diffs = [i for i in range(width) if new[i] != current[i]]
                for i in diffs:
                    self.change_repo.create(record.id, header[i], current[i], new[i], revisor_id, now)
                if diffs:
                    cells_changed += len(diffs)
                    records_changed += 1
                # Marking a page done also records records the revisor looked at and left as is,
                # so the export shows they were confirmed.
                if diffs or (mark_done and record.revised_values is None):
                    self.revision_repo.save(record.id, revisor_id, new, now)

            if mark_done:
                self.review_repo.set(project_id, page, revisor_id, now)
            elif cells_changed:
                self.review_repo.delete(project_id, page, revisor_id)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        return SaveResult(page=page, pages=pages, cells_changed=cells_changed,
                          records_changed=records_changed)

    def get_done_pages(self, project_id: int, revisor_id: int) -> Set[int]:
        return self.review_repo.get_done_pages(project_id, revisor_id)


class DefaultProgressService(ProgressService):
    def __init__(self, progress_repo: ProgressRepository, page_size: int):
        self.progress_repo = progress_repo
        self.page_size = page_size

    def for_revisor(self, revisor_id: int) -> List[RevisorProjectProgress]:
        return self.progress_repo.revisor_progress(revisor_id, self.page_size)

    def for_admin(self) -> List[ProjectProgressReport]:
        reports = {
            p["project_id"]: ProjectProgressReport(
                project_id=p["project_id"], project_name=p["project_name"],
                total_records=p["total_records"], pages=p["pages"], rows=[],
            )
            for p in self.progress_repo.project_totals(self.page_size)
        }
        for r in self.progress_repo.revisor_rows(self.page_size):
            report = reports.get(r["project_id"])
            if report is None:
                continue
            done = min(r["pages_done"], report.pages)
            report.rows.append(RevisorProgressRow(
                user_id=r["user_id"], email=r["email"], pages_done=done,
                pct=int(100 * done / report.pages), records_revised=r["records_revised"],
                last_activity=r["last_activity"],
            ))
        return list(reports.values())


class DefaultAdminService(AdminService):
    def __init__(self, change_repo: ChangeRepository, uow: UnitOfWork):
        self.change_repo = change_repo
        self.uow = uow

    def get_changes(self, project_id: Optional[int] = None) -> List[Change]:
        return self.change_repo.get_recent(project_id)
