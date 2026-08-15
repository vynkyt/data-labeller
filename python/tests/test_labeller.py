import pytest
from fastapi.testclient import TestClient


class MockCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class MockDB:
    """Scripted fake for turso/libsql conn.

    Each execute() pops the next result-set from `results` (defaults to empty).
    Records every call for assertions.
    """

    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        rows = self.results.pop(0) if self.results else []
        return MockCursor(rows)

    def commit(self):
        self.commits += 1


@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def client(mock_db):
    from unittest.mock import patch

    with patch("main.conn", mock_db):
        from main import app

        yield TestClient(app), mock_db


OPEN_TASK_ROW = ("tid1", "http://img", "c1", "j1", None, None, "cat1", "open", None)


# === GET /task ===

def test_get_task_open_task_returned_and_locked(client):
    tc, db = client
    db.results.append([OPEN_TASK_ROW])

    resp = tc.get("/task")

    assert resp.status_code == 200
    task = resp.json()["task"][0]
    assert task["task_id"] == "tid1"
    assert task["url"] == "http://img"
    assert task["categories"] == "cat1"
    assert task["status"] == "open"

    sql, params = db.calls[1]
    assert "UPDATE Task SET status = 'labelling'" in sql
    assert params == ["tid1"]
    assert db.commits == 1


def test_get_task_no_open_tasks_returns_message(client):
    tc, db = client
    db.results.append([])

    resp = tc.get("/task")

    assert resp.status_code == 200
    assert resp.json() == {"message": "there are no open tasks"}
    assert db.commits == 0


def test_get_task_multiple_rows_only_first_locked(client):
    tc, db = client
    other = ("tid2", "http://img2", "c1", "j1", None, None, "cat1", "open", None)
    db.results.append([OPEN_TASK_ROW, other])

    resp = tc.get("/task")

    assert len(resp.json()["task"]) == 2
    sql, params = db.calls[1]
    assert params == ["tid1"]


def test_get_task_labelling_task_not_returned(client):
    tc, db = client
    db.results.append([])

    resp = tc.get("/task")

    assert resp.json() == {"message": "there are no open tasks"}
    assert not any("UPDATE Task" in sql for sql, _ in db.calls)


# === POST /updatelabel ===

def test_updatelabel_happy(client):
    tc, db = client

    resp = tc.post("/updatelabel", json={
        "task_id": "tid1", "labeller_id": "lab1", "label": ["cat1"]
    })

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    sql, params = db.calls[0]
    assert "status = 'labelled'" in sql
    assert params == (str(["cat1"]), "lab1", "tid1")
    assert db.commits == 1


def test_updatelabel_multiple_categories(client):
    tc, db = client

    resp = tc.post("/updatelabel", json={
        "task_id": "tid1", "labeller_id": "lab1", "label": ["a", "b"]
    })

    assert resp.json() == {"status": "success"}
    assert db.calls[0][1][0] == str(["a", "b"])


def test_updatelabel_unknown_task_still_success(client):
    tc, db = client

    resp = tc.post("/updatelabel", json={
        "task_id": "nope", "labeller_id": "lab1", "label": ["cat1"]
    })

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    assert db.calls[0][1][2] == "nope"


def test_updatelabel_empty_label_list(client):
    tc, db = client

    resp = tc.post("/updatelabel", json={
        "task_id": "tid1", "labeller_id": "lab1", "label": []
    })

    assert resp.json() == {"status": "success"}
    assert db.calls[0][1][0] == "[]"


def test_updatelabel_relabel_after_labelled(client):
    tc, db = client
    resp = tc.post("/updatelabel", json={
        "task_id": "tid1", "labeller_id": "lab1", "label": ["new"]
    })

    assert resp.json() == {"status": "success"}
    sql, params = db.calls[0]
    assert params == (str(["new"]), "lab1", "tid1")


def test_updatelabel_unicode_label(client):
    tc, db = client

    resp = tc.post("/updatelabel", json={
        "task_id": "tid1", "labeller_id": "lab1", "label": ["café", "naïve"]
    })

    assert resp.json() == {"status": "success"}
    assert db.calls[0][1][0] == str(["café", "naïve"])


# === GET /countlabelled ===

def test_countlabelled_all_labelled_returns_tasks(client):
    tc, db = client
    db.results = [
        [("j1",)],
        [(1,)],
        [(1,)],
        [("t1", "u1", "c1", "j1", "lab1", "['cat1']", "cat1", "labelled", None)],
    ]

    resp = tc.get("/countlabelled")

    assert resp.status_code == 200
    assert resp.json() == [["t1", "u1", "c1", "j1", "lab1", "['cat1']", "cat1", "labelled", None]]
    assert db.calls[0][0] == "SELECT job_id from AI"


def test_countlabelled_no_jobs_returns_none(client):
    tc, db = client
    db.results = [[]]

    resp = tc.get("/countlabelled")

    assert resp.status_code == 200
    assert resp.json() is None


def test_countlabelled_partial_returns_none(client):
    tc, db = client
    db.results = [
        [("j1",)],
        [(1,)],
        [(2,)],
    ]

    resp = tc.get("/countlabelled")

    assert resp.json() is None


def test_countlabelled_first_complete_job_wins(client):
    tc, db = client
    j1_tasks = [
        ("t1", "u1", "c1", "j1", "lab1", "['a']", "a", "labelled", None),
        ("t2", "u2", "c1", "j1", "lab1", "['a']", "a", "labelled", None),
    ]
    db.results = [
        [("j1",), ("j2",)],
        [(2,)],
        [(2,)],
        j1_tasks,
    ]

    resp = tc.get("/countlabelled")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(row[3] == "j1" for row in data)


def test_countlabelled_zero_tasks_labelled(client):
    tc, db = client
    db.results = [
        [("j1",)],
        [(0,)],
        [(3,)],
    ]

    resp = tc.get("/countlabelled")

    assert resp.json() is None


# === run_aiqc (AI QC pass) ===

def task_row(tid, lab, status="labelled"):
    return (tid, "http://img", "c1", "j1", lab, "['cat1']", "cat1", status, None)


@pytest.fixture
def qc(monkeypatch, mock_db):
    from unittest.mock import patch

    monkeypatch.setattr("main.gemini_check", lambda task: None)
    with patch("main.conn", mock_db):
        import main as m

        yield m, mock_db


def test_qc_incomplete_job_skipped(qc):
    m, db = qc
    db.results = [
        [("j1", 2, 0, None)],
        [(1,)],
    ]

    m.run_aiqc()

    assert not any("UPDATE AI" in sql for sql, _ in db.calls)
    assert db.commits == 0


def test_qc_zero_tasks_processed(qc):
    m, db = qc
    db.results = [
        [("j1", 0, 0, None)],
        [],
    ]

    m.run_aiqc()

    sql, params = db.calls[1]
    assert "ai_processed = 1" in sql
    assert db.commits == 1


def test_qc_no_jobs_noop(qc):
    m, db = qc
    db.results = [[]]

    m.run_aiqc()

    assert db.calls == [("SELECT job_id, total_tasks, ai_processed, bad_labellers FROM AI", None)]
    assert db.commits == 0


def test_qc_pass_keeps_labelled(qc):
    m, db = qc
    m.gemini_check = lambda task: True
    db.results = [
        [("j1", 1, 0, None)],
        [(1,)],
        [task_row("t1", "lab1")],
        [],
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)
    sql, params = db.calls[3]
    assert "ai_processed = 1" in sql
    assert params[1] == "j1"


def test_qc_fail_flags_labeller_and_qc_open_all(qc):
    m, db = qc
    m.gemini_check = lambda task: False
    db.results = [
        [("j1", 1, 0, None)],
        [(1,)],
        [task_row("t1", "lab1")],
        [],
        [],
    ]

    m.run_aiqc()

    qc_updates = [p for sql, p in db.calls if "qc_open" in sql]
    assert qc_updates == [("j1", "lab1")], qc_updates
    ai_update = [p for sql, p in db.calls if "UPDATE AI" in sql and "bad_labellers" in sql][0]
    assert ai_update == ('["lab1"]', "j1")


def test_qc_bad_labeller_skips_gemini_straight_to_qc_open(qc):
    m, db = qc
    reviewed = []
    m.gemini_check = lambda task: reviewed.append(task) or True
    db.results = [
        [("j1", 1, 0, '["lab1"]')],
        [(1,)],
        [task_row("t1", "lab1")],
        [],
        [],
    ]

    m.run_aiqc()

    qc_updates = [p for sql, p in db.calls if "qc_open" in sql]
    assert qc_updates == [("t1",)]
    assert reviewed == []


def test_qc_small_job_one_random_task_per_labeller(qc):
    m, db = qc
    reviewed = []
    m.gemini_check = lambda task: reviewed.append(task) or True
    db.results = [
        [("j1", 2, 0, None)],
        [(2,)],
        [task_row("t1", "lab1"), task_row("t2", "lab1")],
        [],
    ]

    m.run_aiqc()

    assert len(reviewed) == 1
    assert reviewed[0][0] in ("t1", "t2")


def test_qc_large_job_dice_reviews_selected(qc, monkeypatch):
    m, db = qc
    m.QC_DICE_FIXED = 5
    monkeypatch.setattr("main.random.randint", lambda a, b: 5)
    m.gemini_check = lambda task: True
    rows = [task_row(f"t{i}", "lab1") for i in range(10)]
    db.results = [
        [("j1", 10, 0, None)],
        [(10,)],
        rows,
        [],
    ]

    m.run_aiqc()

    assert any("ai_processed = 1" in sql for sql, _ in db.calls)


def test_qc_large_job_dice_none_selected(qc, monkeypatch):
    m, db = qc
    m.QC_DICE_FIXED = 5
    monkeypatch.setattr("main.random.randint", lambda a, b: 4)
    m.gemini_check = lambda task: False
    rows = [task_row(f"t{i}", "lab1") for i in range(10)]
    db.results = [
        [("j1", 10, 0, None)],
        [(10,)],
        rows,
        [],
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)
    assert any("ai_processed = 1" in sql for sql, _ in db.calls)


def test_qc_gemini_skipped_keeps_labelled(qc):
    m, db = qc
    m.gemini_check = lambda task: None
    db.results = [
        [("j1", 1, 0, None)],
        [(1,)],
        [task_row("t1", "lab1")],
        [],
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)
    assert any("ai_processed = 1" in sql for sql, _ in db.calls)
