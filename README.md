# CSV Revision App

A Flask web app where an **admin** uploads a CSV and **revisors** review it page by page.
Every revisor works independently on their own copy of the data. The admin follows each
revisor's progress and downloads one CSV with the original data plus every revisor's work.

Ready to deploy on **PythonAnywhere** (steps below) or to run locally.

## How it works

**Admin**
1. Logs in (the account is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`).
2. Uploads a CSV. The first row is the header; every other row is a record.
3. **Optionally define label options** for any column as JSON (e.g. `{"Status": ["Open", "Closed"], "Priority": ["Low", "High"]}`). Revisors will see dropdown selectors for those columns instead of free-text inputs.
4. Watches each revisor's progress on the **Progress** page.
5. Downloads the combined CSV for a project.

**Revisor**
1. Registers at `/register`, then logs in.
2. Opens a project. Records are shown **10 per page**.
3. Changes whatever needs changing, then saves the page:
   - **Save draft**: keeps the edits, page is not marked done.
   - **Save & mark page done**: saves and marks the page done.
   - **Save & next page**: same, then opens the next page.
4. Can add **Notes** for each record (free-text textarea).
5. Sees their own progress in every project (pages done, records saved, "Continue" button).

**Independence.** Each revisor has their own saved version of every record. One revisor's edits,
progress and "done" pages never affect another's, and the original data is never modified.

## Progress

| Who | Where | What |
|-----|-------|------|
| Revisor | Projects page and top of each project page | Pages done / total, records saved / total, progress bar |
| Admin | **Progress** page | Per project, per revisor: pages done, %, records saved, last activity (UTC). Revisors who have not started show 0 |

A page counts as done when the revisor uses *Save & mark page done* or *Save & next page*.
Saving a draft with changes on a page that was done un-marks it, so "done" always means
"saved exactly as shown".

## Downloaded CSV

First the original columns. Then, for **each revisor who saved something in that project**, four groups of columns:

| Column | Content |
|--------|---------|
| `Revisor email (alice@x.com)` | the revisor's email, filled on every record they saved |
| `<each original column> (alice@x.com)` | the values the revisor saved for that record |
| `Note (alice@x.com)` | the note the revisor entered for that record |
| `Revised at UTC (alice@x.com)` | when the revisor last saved that record |

Example for columns `Name,Note` and revisors alice and bob:

```
Name,Note,Revisor email (alice@x.com),Name (alice@x.com),Note (alice@x.com),Note (alice@x.com),Revised at UTC (alice@x.com),Revisor email (bob@x.com),Name (bob@x.com),Note (bob@x.com),Note (bob@x.com),Revised at UTC (bob@x.com)
Ali,hello,alice@x.com,Ali,hello there,looks good,2026-11-17 12:30:05,,,,
```

- A record the revisor never saved has blank cells in their columns.
- When a page is marked done, every record on it is saved for that revisor, including records left
  unchanged, so the file shows the revisor looked at them. "Save draft" only stores records that were changed.
- The file is UTF-8 with a BOM, so Excel shows Arabic and other non-Latin text correctly.
- Text a revisor typed that starts with `=`, `@` (or `+`/`-` followed by non-numeric text) gets a leading `'`
  so Excel cannot run it as a formula.
- The **Changes** page keeps a full audit log of every edited cell (old value, new value, who, when).
- If label options were defined for a project, a comment row `# LABELS: ...` is prepended to the CSV.

## Configuration (`.env`)

Copy `.env.example` to `.env` and fill it in. `.env` is in `.gitignore`; never commit or share it.

| Variable | Required | Meaning |
|----------|----------|---------|
| `SECRET_KEY` | yes | Random, 32+ characters. The app will not start without it. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | on first start | Creates the admin when none exists (password 8+ characters). The app will not start on an empty database without them. |
| `ALLOW_REGISTRATION` | no | `true` (default): revisors register themselves. `false`: self-registration is disabled. |
| `SECURE_COOKIES` | no | `true` (default) on HTTPS. Use `false` only for plain `http://localhost`. |
| `DATABASE_PATH` | no | Location of the SQLite file. Default: `revision.db` next to `app.py`. |

Generate a secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Revisors can never become admin by registering: registration always creates a revisor.

## Column Labels (Dropdown Selection)

When uploading a CSV, the admin can optionally provide a **Labels** JSON mapping column names to
arrays of allowed options. Revisors will then see a dropdown selector for those columns instead of
a free-text textarea.

**Example:**
```json
{
  "Status": ["Open", "Closed", "Pending"],
  "Priority": ["Low", "Medium", "High"]
}
```

- Only columns listed in the JSON get dropdowns; other columns remain as textareas.
- The selected value is saved as plain text (same as if typed manually).
- The exported CSV includes a comment row `# LABELS: Status: Open, Closed, Pending; Priority: Low, Medium, High`
  so the label definitions are preserved.

## Revisor Notes

Each record has a **Notes** column (textarea, 2 rows) where revisors can enter free-text comments.
Notes are saved per-revisor per-record and included in the exported CSV as `Note (email)` columns.

## Deploy on PythonAnywhere

Replace `YOURUSERNAME` with your PythonAnywhere username. Python 3.10 or newer is required.

1. **Upload the code.** In a **Bash console** run `git clone <your repo> csv_revision`, or upload the
   `csv_revision` folder from the **Files** tab. It must be at `/home/YOURUSERNAME/csv_revision`.

2. **Create a virtualenv and install the dependencies:**

   ```bash
   cd ~/csv_revision
   python3.12 -m venv ~/.virtualenvs/csv_revision      # or python3.10 / python3.11
   source ~/.virtualenvs/csv_revision/bin/activate
   pip install -r requirements.txt
   ```

3. **Create `.env`** (it is not in git, so create it on the server):

   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_hex(32))"   # copy the output
   nano .env     # set SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD; keep SECURE_COOKIES=true
   ```

4. **Create the web app.** **Web** tab → **Add a new web app** → **Manual configuration** →
   the same Python version as in step 2.

5. **Virtualenv:** on the Web tab enter `/home/YOURUSERNAME/.virtualenvs/csv_revision`.

6. **WSGI file:** on the Web tab open the WSGI configuration file
   (`/var/www/YOURUSERNAME_pythonanywhere_com_wsgi.py`), delete its contents and paste in the
   contents of `wsgi.py`. No edits needed.

7. *(Optional, faster static files)* Web tab → **Static files**: URL `/static/`,
   directory `/home/YOURUSERNAME/csv_revision/static`.

8. Press **Reload**, open `https://YOURUSERNAME.pythonanywhere.com` and log in as the admin.
   If the page shows an error, read the **Error log** link on the Web tab: a missing
   `SECRET_KEY` or admin setting is reported there in plain words.

After the first successful start you can delete `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.
After changing code or `.env`, press **Reload**.

### Backups and updates

- All data is in one SQLite file (`revision.db`, or `DATABASE_PATH`). Download it from the
  **Files** tab to back it up. It is excluded from git.
- To update, replace the code files (keep `.env` and `revision.db`), run
  `pip install -r requirements.txt` again if requirements changed, then press **Reload**.
  Tables and indexes are created automatically.
- Upgrading from the earlier version: the database still opens and the admin account is kept, but revisor
  edits made in the earlier version are not carried over (they are stored differently now).

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # set SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
                                     # and SECURE_COOKIES=false for http://localhost
python app.py                        # http://127.0.0.1:5000
```

Run the tests (they use a temporary database):

```bash
python -m unittest -v
```

## CSV requirements

- UTF-8 (a BOM is fine). In Excel: *Save as → CSV UTF-8 (Comma delimited)*.
- Comma, semicolon or tab separated (detected from the header row).
- Maximum 10 MB and 500 columns. Short rows are padded; a row with extra non-empty cells is rejected with its row number.
- Empty rows are skipped.

## Routes

| Method | Path | Who | Purpose |
|--------|------|-----|---------|
| GET/POST | `/register` | public (if `ALLOW_REGISTRATION=true`) | Revisor registration |
| GET/POST | `/login` | public | Sign in (10 failed attempts per 15 minutes per IP, then HTTP 429) |
| POST | `/logout` | signed in | Sign out |
| GET | `/projects` | signed in | Admin: upload form and project list. Revisor: own progress |
| POST | `/upload` | admin | Upload a CSV as a new project |
| GET/POST | `/projects/<id>?page=N` | revisor | View and save page N |
| GET | `/admin/progress` | admin | Progress of every revisor in every project |
| GET | `/admin/export/<id>` | admin | Download the combined CSV |
| GET | `/admin/changes?project=<id>` | admin | Audit log of edited cells |

## Security

- Passwords: PBKDF2-SHA256 hashes; passwords must be 8 to 128 characters.
- Sessions: HTTP-only, `SameSite=Lax`, `Secure` on HTTPS, expire after 12 hours.
- CSRF token on every form, including logout.
- Login attempts are rate limited and registration is limited to 20 per hour per IP.
  Counters are kept in memory per worker process; with several workers each counts separately.
- All SQL uses parameter placeholders; templates escape all values.
- Admin pages return 403 to revisors; admins are sent back to the project list if they open a revision page.
- Responses carry `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and a same-origin referrer policy.
- If `.env` was ever shared, generate a new `SECRET_KEY` (this signs everyone out) and change the admin password.

## Limitations

- There is no password-change or password-reset page. To reset a password, create a new account
  or change the hash directly in the database.
- Every revisor sees every project; there is no per-project assignment.
- Pages are fixed at 10 records (`PAGE_SIZE` in `app.py`).

## Project layout

```
csv_revision/
├── app.py                 # Config, database schema, admin creation, error pages
├── wsgi.py                # PythonAnywhere entry point
├── .env.example           # Template for your private .env
├── requirements.txt
├── models/                # Plain data classes
├── repositories/          # interfaces.py (contracts) + sqlite.py (SQLite implementation)
├── services/              # interfaces.py, impl.py (business rules), csv_utils.py (upload parsing)
├── views/                 # Flask blueprints: auth, project (revisors), admin
├── templates/             # Jinja2 pages
├── static/                # style.css, autosize.js, page.js
└── tests/                 # End-to-end tests of the workflow
```

Data tables: `users`, `projects`, `records` (original rows, never changed), `revisions` (one saved
version of a record per revisor, with timestamp), `page_reviews` (pages a revisor marked done) and
`changes` (audit log).
