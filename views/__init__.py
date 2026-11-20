import csv
import io
from functools import wraps

from flask import (
    Blueprint, request, redirect, url_for, session, flash, abort, Response, g, render_template,
)

from models import User
from repositories.sqlite import (
    SQLiteUnitOfWork, SQLiteUserRepository, SQLiteProjectRepository, SQLiteRecordRepository,
    SQLiteRevisionRepository, SQLitePageReviewRepository, SQLiteChangeRepository,
    SQLiteProgressRepository,
)
from services.csv_utils import parse_csv
from services.impl import (
    DefaultAuthService, DefaultProjectService, DefaultRecordService,
    DefaultProgressService, DefaultAdminService,
)


def create_blueprints(get_db, allow_registration: bool, page_size: int, limiter):
    """Build the blueprints. The database accessor and limiter are passed in, so this
    package never imports the app module back."""

    auth_bp = Blueprint("auth", __name__)
    project_bp = Blueprint("project", __name__)
    admin_bp = Blueprint("admin", __name__)

    def get_services():
        if "services" not in g:
            db = get_db()
            uow = SQLiteUnitOfWork(db)
            user_repo = SQLiteUserRepository(db)
            project_repo = SQLiteProjectRepository(db)
            record_repo = SQLiteRecordRepository(db)
            revision_repo = SQLiteRevisionRepository(db)
            review_repo = SQLitePageReviewRepository(db)
            change_repo = SQLiteChangeRepository(db)
            progress_repo = SQLiteProgressRepository(db)
            g.services = {
                "auth": DefaultAuthService(user_repo, uow),
                "project": DefaultProjectService(project_repo, record_repo, revision_repo, uow),
                "record": DefaultRecordService(record_repo, revision_repo, review_repo, change_repo, uow),
                "progress": DefaultProgressService(progress_repo, page_size),
                "admin": DefaultAdminService(change_repo, uow),
            }
        return g.services

    def current_user() -> User | None:
        if "user_obj" not in g:
            uid = session.get("uid")
            g.user_obj = get_services()["auth"].get_user(uid) if uid else None
        return g.user_obj

    @auth_bp.app_context_processor
    def inject_user():
        try:
            return {"user": current_user()}
        except Exception:
            return {"user": None}

    def login_required(role: str | None = None):
        """role: None = any signed-in user, "admin" = admins only, "revisor" = non-admins only."""
        def decorator(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                user = current_user()
                if user is None:
                    return redirect(url_for("auth.login"))
                if role == "admin" and not user.is_admin:
                    abort(403)
                if role == "revisor" and user.is_admin:
                    flash("Revising is done from revisor accounts. Admins upload projects, "
                          "follow progress and export.")
                    return redirect(url_for("project.projects"))
                return view(*args, **kwargs)
            return wrapper
        return decorator

    def start_session(user: User):
        session.clear()
        session["uid"] = user.id
        session.permanent = True

    # ---------- authentication ----------

    @auth_bp.route("/register", methods=["GET", "POST"])
    @limiter.limit("20 per hour", methods=["POST"])
    def register():
        if not allow_registration:
            abort(404)
        if current_user() is not None:
            return redirect(url_for("project.projects"))
        if request.method == "POST":
            try:
                user = get_services()["auth"].register(
                    request.form.get("email", ""), request.form.get("password", "")
                )
            except ValueError as exc:
                flash(str(exc))
            else:
                start_session(user)
                return redirect(url_for("project.projects"))
        return render_template("auth.html", title="Register", allow_registration=allow_registration)

    @auth_bp.route("/login", methods=["GET", "POST"])
    @limiter.limit("10 per 15 minutes", methods=["POST"],
                   deduct_when=lambda response: response.status_code != 302)
    def login():
        if current_user() is not None:
            return redirect(url_for("project.projects"))
        if request.method == "POST":
            user = get_services()["auth"].login(
                request.form.get("email", ""), request.form.get("password", "")
            )
            if user:
                start_session(user)
                return redirect(url_for("project.projects"))
            flash("Wrong email or password.")
        return render_template("auth.html", title="Login", allow_registration=allow_registration)

    @auth_bp.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("auth.login"))

    # ---------- projects ----------

    @project_bp.route("/")
    @project_bp.route("/projects")
    @login_required()
    def projects():
        user = current_user()
        progress = get_services()["progress"]
        if user.is_admin:
            return render_template("admin_projects.html", reports=progress.for_admin())
        return render_template("revisor_projects.html", progress=progress.for_revisor(user.id))

    @project_bp.route("/upload", methods=["POST"])
    @login_required(role="admin")
    def upload():
        upload_file = request.files.get("file")
        if upload_file is None or not upload_file.filename:
            flash("Choose a CSV file to upload.")
            return redirect(url_for("project.projects"))
        try:
            header, rows = parse_csv(upload_file.read())
            labels = {}
            labels_text = request.form.get("labels", "").strip()
            if labels_text:
                import json
                try:
                    labels = json.loads(labels_text)
                except json.JSONDecodeError:
                    flash("Labels must be valid JSON object mapping column names to arrays of options.")
                    return redirect(url_for("project.projects"))
            get_services()["project"].create_project(request.form.get("name", ""), header, rows, labels)
        except ValueError as exc:
            flash(str(exc))
        else:
            flash(f"Uploaded {len(rows)} records in {len(header)} columns.")
        return redirect(url_for("project.projects"))

    @project_bp.route("/projects/<int:pid>", methods=["GET", "POST"])
    @login_required(role="revisor")
    def project(pid):
        services = get_services()
        user = current_user()
        proj = services["project"].get_project(pid)
        if proj is None:
            abort(404)
        page = request.args.get("page", 1, type=int)

        if request.method == "POST":
            action = request.form.get("action", "draft")
            if action not in ("draft", "done", "next"):
                abort(400)
            result = services["record"].save_page(
                pid, page, page_size, user.id, request.form, proj.header,
                mark_done=action in ("done", "next"),
            )
            changes = f"{result.cells_changed} change(s)" if result.cells_changed else "no changes"
            if action == "draft":
                flash(f"Page {result.page}: draft saved ({changes}).")
            else:
                flash(f"Page {result.page}: saved and marked done ({changes}).")
            target = result.page
            if action == "next" and result.page < result.pages:
                target = result.page + 1
            return redirect(url_for("project.project", pid=pid, page=target))

        records, page, pages = services["record"].get_page(pid, page, page_size, user.id)
        done_pages = services["record"].get_done_pages(pid, user.id)
        mine = next(p for p in services["progress"].for_revisor(user.id) if p.project_id == pid)
        return render_template(
            "page.html", project=proj, header=proj.header, records=records,
            page=page, pages=pages, page_done=page in done_pages,
            done_pages=done_pages, progress=mine,
        )

    # ---------- admin ----------

    @admin_bp.route("/admin/export/<int:pid>")
    @login_required(role="admin")
    def export_project(pid):
        services = get_services()
        proj = services["project"].get_project(pid)
        if proj is None:
            abort(404)
        header, rows = services["project"].export_project(pid)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(rows)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in proj.name) or f"project_{pid}"
        return Response(
            out.getvalue().encode("utf-8-sig"),      # BOM so Excel reads Arabic correctly
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_revised.csv"'},
        )

    @admin_bp.route("/admin/progress")
    @login_required(role="admin")
    def admin_progress():
        return render_template("progress.html", reports=get_services()["progress"].for_admin())

    @admin_bp.route("/admin/changes")
    @login_required(role="admin")
    def admin_changes():
        services = get_services()
        pid = request.args.get("project", type=int)
        return render_template(
            "changes.html", changes=services["admin"].get_changes(pid),
            projects=services["project"].list_projects(), sel=str(pid or ""),
        )

    return auth_bp, project_bp, admin_bp
