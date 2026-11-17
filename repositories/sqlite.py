import json
import math
import sqlite3
from typing import List, Optional, Set

from models import (
    User, Project, Record, Revision, PageReview, Change, DuplicateEmailError,
    RevisorProjectProgress,
)
from repositories.interfaces import (
    UnitOfWork, UserRepository, ProjectRepository, RecordRepository, RevisionRepository,
    PageReviewRepository, ChangeRepository, ProgressRepository,
)


class SQLiteUnitOfWork(UnitOfWork):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()


class SQLiteUserRepository(UserRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._to_user(row) if row else None

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.db.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        return self._to_user(row) if row else None

    def create(self, email: str, password_hash: str, is_admin: bool = False) -> User:
        try:
            cur = self.db.execute(
                "INSERT INTO users(email, password, is_admin) VALUES(?,?,?)",
                (email.lower(), password_hash, 1 if is_admin else 0),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmailError("That email is already registered.") from exc
        return User(id=cur.lastrowid, email=email.lower(), password=password_hash, is_admin=is_admin)

    def get_all(self) -> List[User]:
        rows = self.db.execute("SELECT * FROM users ORDER BY is_admin DESC, email").fetchall()
        return [self._to_user(r) for r in rows]

    def get_revisors(self) -> List[User]:
        rows = self.db.execute("SELECT * FROM users WHERE is_admin=0 ORDER BY email").fetchall()
        return [self._to_user(r) for r in rows]

    @staticmethod
    def _to_user(row: sqlite3.Row) -> User:
        return User(id=row["id"], email=row["email"], password=row["password"],
                    is_admin=bool(row["is_admin"]))


class SQLiteProjectRepository(ProjectRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self.db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._to_project(row) if row else None

    def get_all(self) -> List[Project]:
        rows = self.db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        return [self._to_project(r) for r in rows]

    def create(self, name: str, header: List[str]) -> Project:
        cur = self.db.execute(
            "INSERT INTO projects(name, header) VALUES(?,?)", (name, json.dumps(header))
        )
        return Project(id=cur.lastrowid, name=name, header=header)

    @staticmethod
    def _to_project(row: sqlite3.Row) -> Project:
        return Project(id=row["id"], name=row["name"], header=json.loads(row["header"]))


class SQLiteRecordRepository(RecordRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_page(self, project_id: int, user_id: int, limit: int, offset: int) -> List[Record]:
        rows = self.db.execute(
            "SELECT r.id, r.project_id, r.position, r.original_values_json, "
            "       v.values_json AS revised_json, v.revised_at "
            "FROM records r "
            "LEFT JOIN revisions v ON v.record_id = r.id AND v.user_id = ? "
            "WHERE r.project_id = ? ORDER BY r.position LIMIT ? OFFSET ?",
            (user_id, project_id, limit, offset),
        ).fetchall()
        return [
            Record(
                id=r["id"], project_id=r["project_id"], position=r["position"],
                original_values=json.loads(r["original_values_json"]),
                revised_values=json.loads(r["revised_json"]) if r["revised_json"] else None,
                revised_at=r["revised_at"],
            )
            for r in rows
        ]

    def get_all_by_project(self, project_id: int) -> List[Record]:
        rows = self.db.execute(
            "SELECT id, project_id, position, original_values_json FROM records "
            "WHERE project_id=? ORDER BY position",
            (project_id,),
        ).fetchall()
        return [
            Record(id=r["id"], project_id=r["project_id"], position=r["position"],
                   original_values=json.loads(r["original_values_json"]))
            for r in rows
        ]

    def count_by_project(self, project_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM records WHERE project_id=?", (project_id,)
        ).fetchone()[0]

    def create_batch(self, project_id: int, rows: List[List[str]]) -> None:
        self.db.executemany(
            "INSERT INTO records(project_id, position, original_values_json) VALUES(?,?,?)",
            [(project_id, i, json.dumps(r)) for i, r in enumerate(rows)],
        )


class SQLiteRevisionRepository(RevisionRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def save(self, record_id: int, user_id: int, values: List[str], at: str) -> None:
        self.db.execute(
            "INSERT INTO revisions(record_id, user_id, values_json, revised_at) VALUES(?,?,?,?) "
            "ON CONFLICT(record_id, user_id) DO UPDATE SET "
            "values_json=excluded.values_json, revised_at=excluded.revised_at",
            (record_id, user_id, json.dumps(values), at),
        )

    def get_by_project(self, project_id: int) -> List[Revision]:
        rows = self.db.execute(
            "SELECT v.record_id, v.user_id, u.email, v.values_json, v.revised_at "
            "FROM revisions v "
            "JOIN records r ON r.id = v.record_id "
            "JOIN users u ON u.id = v.user_id "
            "WHERE r.project_id = ? ORDER BY u.email, r.position",
            (project_id,),
        ).fetchall()
        return [
            Revision(record_id=r["record_id"], user_id=r["user_id"], email=r["email"],
                     values=json.loads(r["values_json"]), revised_at=r["revised_at"])
            for r in rows
        ]


class SQLitePageReviewRepository(PageReviewRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get(self, project_id: int, page: int, user_id: int) -> Optional[PageReview]:
        row = self.db.execute(
            "SELECT revised_at FROM page_reviews WHERE project_id=? AND page=? AND user_id=?",
            (project_id, page, user_id),
        ).fetchone()
        return PageReview(project_id, page, user_id, row["revised_at"]) if row else None

    def get_done_pages(self, project_id: int, user_id: int) -> Set[int]:
        rows = self.db.execute(
            "SELECT page FROM page_reviews WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        ).fetchall()
        return {r["page"] for r in rows}

    def set(self, project_id: int, page: int, user_id: int, at: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO page_reviews(project_id, page, user_id, revised_at) VALUES(?,?,?,?)",
            (project_id, page, user_id, at),
        )

    def delete(self, project_id: int, page: int, user_id: int) -> None:
        self.db.execute(
            "DELETE FROM page_reviews WHERE project_id=? AND page=? AND user_id=?",
            (project_id, page, user_id),
        )


class SQLiteChangeRepository(ChangeRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def create(self, record_id: int, col: str, old_value: str, new_value: str,
               user_id: int, at: str) -> None:
        self.db.execute(
            "INSERT INTO changes(record_id, col, old_value, new_value, user_id, changed_at) "
            "VALUES(?,?,?,?,?,?)",
            (record_id, col, old_value, new_value, user_id, at),
        )

    def get_recent(self, project_id: Optional[int] = None, limit: int = 500) -> List[Change]:
        sql = (
            "SELECT c.*, u.email, r.position, p.name AS pname FROM changes c "
            "JOIN users u ON u.id = c.user_id "
            "JOIN records r ON r.id = c.record_id "
            "JOIN projects p ON p.id = r.project_id"
        )
        args: tuple = ()
        if project_id:
            sql += " WHERE r.project_id = ?"
            args = (project_id,)
        sql += " ORDER BY c.id DESC LIMIT ?"
        rows = self.db.execute(sql, args + (limit,)).fetchall()
        return [
            Change(id=r["id"], record_id=r["record_id"], col=r["col"], old_value=r["old_value"],
                   new_value=r["new_value"], user_id=r["user_id"], changed_at=r["changed_at"],
                   email=r["email"], position=r["position"], project_name=r["pname"])
            for r in rows
        ]


class SQLiteProgressRepository(ProgressRepository):
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def _pages(total: int, page_size: int) -> int:
        return max(1, math.ceil(total / page_size))

    def revisor_progress(self, user_id: int, page_size: int) -> List[RevisorProjectProgress]:
        projects = self.db.execute(
            "SELECT p.id, p.name, "
            " (SELECT COUNT(*) FROM records r WHERE r.project_id = p.id) AS total, "
            " (SELECT COUNT(*) FROM revisions v JOIN records r ON r.id = v.record_id "
            "   WHERE r.project_id = p.id AND v.user_id = ?) AS revised "
            "FROM projects p ORDER BY p.id DESC",
            (user_id,),
        ).fetchall()
        done_rows = self.db.execute(
            "SELECT project_id, page FROM page_reviews WHERE user_id=?", (user_id,)
        ).fetchall()
        done_by_project: dict = {}
        for r in done_rows:
            done_by_project.setdefault(r["project_id"], set()).add(r["page"])

        out = []
        for p in projects:
            pages = self._pages(p["total"], page_size)
            done = {pg for pg in done_by_project.get(p["id"], set()) if 1 <= pg <= pages}
            next_page = next((pg for pg in range(1, pages + 1) if pg not in done), pages)
            out.append(RevisorProjectProgress(
                project_id=p["id"], project_name=p["name"], total_records=p["total"],
                pages=pages, pages_done=len(done), records_revised=p["revised"],
                pct=int(100 * len(done) / pages), next_page=next_page,
            ))
        return out

    def project_totals(self, page_size: int) -> List[dict]:
        rows = self.db.execute(
            "SELECT p.id, p.name, "
            " (SELECT COUNT(*) FROM records r WHERE r.project_id = p.id) AS total "
            "FROM projects p ORDER BY p.id DESC"
        ).fetchall()
        return [
            {"project_id": r["id"], "project_name": r["name"], "total_records": r["total"],
             "pages": self._pages(r["total"], page_size)}
            for r in rows
        ]

    def revisor_rows(self, page_size: int) -> List[dict]:
        rows = self.db.execute(
            "SELECT p.id AS pid, u.id AS uid, u.email, "
            " (SELECT COUNT(*) FROM page_reviews pr WHERE pr.project_id = p.id AND pr.user_id = u.id) AS done, "
            " (SELECT COUNT(*) FROM revisions v JOIN records r ON r.id = v.record_id "
            "   WHERE r.project_id = p.id AND v.user_id = u.id) AS revised, "
            " (SELECT MAX(v.revised_at) FROM revisions v JOIN records r ON r.id = v.record_id "
            "   WHERE r.project_id = p.id AND v.user_id = u.id) AS last "
            "FROM projects p CROSS JOIN users u WHERE u.is_admin = 0 "
            "ORDER BY p.id DESC, u.email"
        ).fetchall()
        return [
            {"project_id": r["pid"], "user_id": r["uid"], "email": r["email"],
             "pages_done": r["done"], "records_revised": r["revised"], "last_activity": r["last"]}
            for r in rows
        ]
