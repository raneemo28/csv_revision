"""End-to-end tests for the admin / revisor workflow. Run with:  python -m unittest -v"""
import csv
import io
import os
import re
import sys
import tempfile
import unittest
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ.update({
    "SECRET_KEY": "x" * 40,
    "ADMIN_EMAIL": "admin@test.com",
    "ADMIN_PASSWORD": "adminpass123",
    "ALLOW_REGISTRATION": "true",
    "SECURE_COOKIES": "false",
    "DATABASE_PATH": os.path.join(_TMP, "test.db"),
})

import app as app_module  # noqa: E402

# 25 records -> 3 pages of 10/10/5. Includes Arabic text and a multi-line cell.
ROWS = [["Name", "Note"]] + [[f"Person {i}", f"note {i}"] for i in range(1, 26)]
ROWS[1] = ["أحمد", "line1\nline2"]
BUF = io.StringIO()
csv.writer(BUF).writerows(ROWS)
CSV_BYTES = BUF.getvalue().encode("utf-8-sig")


def token(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class Client:
    def __init__(self):
        self.c = app_module.app.test_client()

    def get(self, url):
        return self.c.get(url)

    def login(self, email, password):
        html = self.c.get("/login").get_data(as_text=True)
        return self.c.post("/login", data={"email": email, "password": password,
                                           "csrf_token": token(html)})

    def register(self, email, password):
        html = self.c.get("/register").get_data(as_text=True)
        return self.c.post("/register", data={"email": email, "password": password,
                                              "csrf_token": token(html)})


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = Client()
        assert cls.admin.login("admin@test.com", "adminpass123").status_code == 302
        html = cls.admin.get("/projects").get_data(as_text=True)
        r = cls.admin.c.post("/upload", data={
            "name": "Demo", "csrf_token": token(html),
            "file": (io.BytesIO(CSV_BYTES), "demo.csv"),
        }, content_type="multipart/form-data")
        assert r.status_code == 302

        cls.alice = Client()
        cls.bob = Client()
        assert cls.alice.register("alice@x.com", "alicepass123").status_code == 302
        assert cls.bob.register("bob@x.com", "bobpass12345").status_code == 302

    def page(self, who, n):
        return who.get(f"/projects/1?page={n}").get_data(as_text=True)

    def save(self, who, n, action, edits=None):
        html = self.page(who, n)
        # resubmit what the page shows, then apply edits {(record_index_on_page, col): value}
        vals = re.findall(r'<textarea[^>]*name="(c_\d+_\d+)"[^>]*>\n?(.*?)</textarea>', html, re.S)
        data = {name: unescape(v) for name, v in vals}
        names = [n_ for n_, _ in vals]
        for (rec_idx, col), value in (edits or {}).items():
            data[names[rec_idx * 2 + col]] = value
        data["action"] = action
        data["csrf_token"] = token(html)
        return who.c.post(f"/projects/1?page={n}", data=data)

    # 1 ----------------------------------------------------------------
    def test_01_roles(self):
        self.assertEqual(self.alice.get("/admin/progress").status_code, 403)
        self.assertEqual(self.alice.get("/admin/export/1").status_code, 403)
        self.assertEqual(self.admin.get("/projects/1").status_code, 302)  # admins don't revise
        self.assertEqual(Client().get("/projects").status_code, 302)       # anonymous -> login

    def test_02_pages_have_ten_records(self):
        html = self.page(self.alice, 1)
        self.assertEqual(len(re.findall(r'name="c_\d+_0"', html)), 10)
        self.assertEqual(len(re.findall(r'name="c_\d+_0"', self.page(self.alice, 3))), 5)
        self.assertIn("أحمد", html)

    def test_03_independent_revisors_and_progress(self):
        # alice edits page 1 and marks it done; bob edits the same record differently, page 2 draft
        self.assertEqual(self.save(self.alice, 1, "done", {(1, 1): "ALICE EDIT"}).status_code, 302)
        self.assertEqual(self.save(self.bob, 1, "draft", {(1, 1): "BOB EDIT"}).status_code, 302)
        self.assertEqual(self.save(self.bob, 2, "done").status_code, 302)

        self.assertIn("ALICE EDIT", self.page(self.alice, 1))
        self.assertNotIn("BOB EDIT", self.page(self.alice, 1))
        self.assertIn("BOB EDIT", self.page(self.bob, 1))
        self.assertNotIn("ALICE EDIT", self.page(self.bob, 1))

        # unchanged multi-line cell must not be reported as a change
        changes = self.admin.get("/admin/changes").get_data(as_text=True)
        self.assertEqual(changes.count("line1"), 0)

        pa = self.alice.get("/projects").get_data(as_text=True)
        pb = self.bob.get("/projects").get_data(as_text=True)
        self.assertIn("1 / 3 pages done", pa)      # alice: page 1
        self.assertIn("1 / 3 pages done", pb)      # bob: page 2 only (page 1 is a draft)
        self.assertIn("page 1)", pb)               # bob's next unfinished page is 1
        self.assertIn("page 2)", pa)

    def test_04_editing_a_done_page_as_draft_clears_done(self):
        self.save(self.alice, 3, "done")
        self.assertIn("2 / 3 pages done", self.alice.get("/projects").get_data(as_text=True))
        self.save(self.alice, 3, "draft", {(0, 0): "changed again"})
        self.assertIn("1 / 3 pages done", self.alice.get("/projects").get_data(as_text=True))
        self.save(self.alice, 3, "done")                       # restore for later tests
        self.assertIn("2 / 3 pages done", self.alice.get("/projects").get_data(as_text=True))

    def test_05_admin_progress(self):
        html = self.admin.get("/admin/progress").get_data(as_text=True)
        self.assertIn("alice@x.com", html)
        self.assertIn("bob@x.com", html)
        self.assertRegex(html, r"alice@x\.com</td>\s*<td>2 / 3</td>")

    def test_06_export(self):
        r = self.admin.get("/admin/export/1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
        header = rows[0]
        self.assertEqual(header[:2], ["Name", "Note"])
        self.assertIn("Revisor email (alice@x.com)", header)
        self.assertIn("Note (alice@x.com)", header)
        self.assertIn("Revised at UTC (alice@x.com)", header)
        self.assertIn("Revisor email (bob@x.com)", header)
        self.assertEqual(len(rows) - 1, 25)

        a = header.index("Revisor email (alice@x.com)")
        b = header.index("Revisor email (bob@x.com)")
        row2 = rows[2]                                          # record 2 (edited by both)
        self.assertEqual(row2[a], "alice@x.com")
        self.assertEqual(row2[a + 2], "ALICE EDIT")
        self.assertRegex(row2[a + 3], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.assertEqual(row2[b + 2], "BOB EDIT")
        self.assertEqual(rows[1][0], "أحمد")                    # original untouched
        # bob never saved record 25 (page 3): his cells are blank, alice's are filled
        last = rows[25]
        self.assertEqual(last[b], "")
        self.assertEqual(last[a], "alice@x.com")

    def test_07_formula_injection_is_neutralised(self):
        self.save(self.bob, 3, "done", {(0, 1): "=HYPERLINK(\"http://evil\")"})
        rows = list(csv.reader(io.StringIO(self.admin.get("/admin/export/1").data.decode("utf-8-sig"))))
        b = rows[0].index("Revisor email (bob@x.com)")
        self.assertTrue(rows[21][b + 2].startswith("'="))

    def test_08_registration_rules(self):
        c = Client()
        self.assertEqual(c.register("alice@x.com", "somepassword1").status_code, 200)   # duplicate
        self.assertEqual(c.register("bad-email", "somepassword1").status_code, 200)
        self.assertEqual(c.register("new@x.com", "short").status_code, 200)
        self.assertEqual(c.register("new@x.com", "longenough1").status_code, 302)

    def test_09_bad_uploads(self):
        html = self.admin.get("/projects").get_data(as_text=True)
        for payload in (b"\xff\xfe\x00bad", b"onlyheader\n", b"a,b\n1,2,3\n"):
            r = self.admin.c.post("/upload", data={
                "name": "bad", "csrf_token": token(html),
                "file": (io.BytesIO(payload), "bad.csv")}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 302)
        projects = self.admin.get("/projects").get_data(as_text=True)
        self.assertNotIn(">bad<", projects)

    def test_10_semicolon_csv(self):
        html = self.admin.get("/projects").get_data(as_text=True)
        self.admin.c.post("/upload", data={
            "name": "Semi", "csrf_token": token(html),
            "file": (io.BytesIO("A;B\n1;2\n".encode()), "s.csv")}, content_type="multipart/form-data")
        self.assertIn(">Semi<", self.admin.get("/projects").get_data(as_text=True))

    def test_99_login_rate_limit(self):
        app_module.limiter.reset()
        c = Client()
        codes = [c.login("alice@x.com", "wrong").status_code for _ in range(12)]
        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10:], [429, 429])
        app_module.limiter.reset()
        self.assertEqual(c.login("alice@x.com", "alicepass123").status_code, 302)


if __name__ == "__main__":
    unittest.main()
