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


OPEN_TASK_ROW = ("tid1", "http://img", "c1", "j1", None, None, "cat1", "open", None, None, None, 0)


# === GET /task ===

def test_get_task_open_task_returned_and_locked(client):
    tc, db = client
    # calls: staleness UPDATE, SELECT open task, UPDATE labelling
    db.results.append([])  # staleness reset
    db.results.append([OPEN_TASK_ROW])  # SELECT open task
    db.results.append([])  # UPDATE labelling

    resp = tc.get("/task")

    assert resp.status_code == 200
    task = resp.json()["task"][0]
    assert task["task_id"] == "tid1"
    assert task["url"] == "http://img"
    assert task["categories"] == "cat1"
    assert task["status"] == "open"

    sql, params = db.calls[2]
    assert "UPDATE Task SET status = 'labelling'" in sql
    assert "locked_at" in sql
    assert params[-1] == "tid1"  # task_id is last param
    assert db.commits >= 1


def test_get_task_no_open_tasks_returns_message(client):
    tc, db = client
    db.results.append([])  # staleness reset
    db.results.append([])  # SELECT open task

    resp = tc.get("/task")

    assert resp.status_code == 200
    assert resp.json() == {"message": "there are no open tasks"}
    assert db.commits == 1  # staleness reset commits


def test_get_task_multiple_rows_only_first_locked(client):
    tc, db = client
    other = ("tid2", "http://img2", "c1", "j1", None, None, "cat1", "open", None, None, None, 0)
    db.results.append([])  # staleness reset
    db.results.append([OPEN_TASK_ROW, other])  # SELECT open task
    db.results.append([])  # UPDATE labelling

    resp = tc.get("/task")

    assert len(resp.json()["task"]) == 2
    sql, params = db.calls[2]
    assert params[-1] == "tid1"  # task_id is last param


def test_get_task_labelling_task_not_returned(client):
    tc, db = client
    db.results.append([])  # staleness reset
    db.results.append([])  # SELECT open task (empty)

    resp = tc.get("/task")

    assert resp.json() == {"message": "there are no open tasks"}
    # No UPDATE should set status TO 'labelling' (staleness reset sets it FROM 'labelling')
    assert not any("SET status = 'labelling'" in sql for sql, _ in db.calls)


# === GET /task with labeller_id (resume feature) ===

LABELLING_TASK_ROW = ("tid1", "http://img", "c1", "j1", "alice", None, "cat1", "labelling", None, "2026-08-15T12:00:00", None, 0)


def test_get_task_with_labeller_id_resumes_existing_task(client):
    tc, db = client
    # staleness reset, then resume SELECT finds labelling task
    db.results.append([])  # staleness reset UPDATE
    db.results.append([LABELLING_TASK_ROW])  # resume SELECT

    resp = tc.get("/task?labeller_id=alice")

    assert resp.status_code == 200
    task = resp.json()["task"][0]
    assert task["task_id"] == "tid1"
    assert task["labeller_id"] == "alice"
    assert task["status"] == "labelling"


def test_get_task_with_labeller_id_no_resume_fetches_new(client):
    tc, db = client
    # staleness reset, resume SELECT returns empty, then SELECT open task, then UPDATE labelling
    db.results.append([])  # staleness reset
    db.results.append([])  # resume SELECT (no existing task)
    db.results.append([OPEN_TASK_ROW])  # SELECT open task
    db.results.append([])  # UPDATE labelling + labeller_id

    resp = tc.get("/task?labeller_id=alice")

    assert resp.status_code == 200
    task = resp.json()["task"][0]
    assert task["task_id"] == "tid1"
    # Verify labeller_id was SET on the UPDATE
    sql, params = db.calls[3]
    assert "labeller_id" in sql
    assert "alice" in params


def test_get_task_without_labeller_id_no_resume(client):
    tc, db = client
    # staleness reset, SELECT open task, UPDATE labelling (no labeller_id)
    db.results.append([])  # staleness reset
    db.results.append([OPEN_TASK_ROW])  # SELECT open task
    db.results.append([])  # UPDATE labelling

    resp = tc.get("/task")

    assert resp.status_code == 200
    sql, params = db.calls[2]
    assert "labeller_id" not in sql
    assert params[-1] == "tid1"  # task_id is last param


def test_get_task_with_labeller_id_no_tasks_available(client):
    tc, db = client
    db.results.append([])  # staleness reset
    db.results.append([])  # resume SELECT (empty)
    db.results.append([])  # SELECT open task (empty)

    resp = tc.get("/task?labeller_id=alice")

    assert resp.json() == {"message": "there are no open tasks"}


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
        [("t1", "u1", "c1", "j1", "lab1", "['cat1']", "cat1", "labelled", None, None, None, 0)],
    ]

    resp = tc.get("/countlabelled")

    assert resp.status_code == 200
    assert resp.json() == [["t1", "u1", "c1", "j1", "lab1", "['cat1']", "cat1", "labelled", None, None, None, 0]]
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
        ("t1", "u1", "c1", "j1", "lab1", "['a']", "a", "labelled", None, None, None, 0),
        ("t2", "u2", "c1", "j1", "lab1", "['a']", "a", "labelled", None, None, None, 0),
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

def task_row(tid, lab, status="labelled", ai_qc_status=None):
    return (tid, "http://img", "c1", "j1", lab, "['cat1']", "cat1", status, None, None, ai_qc_status, 0)


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
        [("j1", 2, None)],
        [(0,)],  # COUNT of unreviewed labelled tasks
    ]

    m.run_aiqc()

    assert not any("UPDATE AI" in sql for sql, _ in db.calls)
    assert db.commits == 0


def test_qc_zero_tasks_processed(qc):
    m, db = qc
    db.results = [
        [("j1", 0, None)],
    ]

    m.run_aiqc()

    assert not any("UPDATE AI" in sql for sql, _ in db.calls)
    assert db.commits == 0


def test_qc_no_jobs_noop(qc):
    m, db = qc
    db.results = [[]]

    m.run_aiqc()

    assert db.calls == [("SELECT job_id, total_tasks, bad_labellers FROM AI", None)]
    assert db.commits == 0


def test_qc_pass_keeps_labelled(qc):
    m, db = qc
    m.gemini_check = lambda task: True
    db.results = [
        [("j1", 1, None)],  # AI row
        [(1,)],  # COUNT unreviewed
        [task_row("t1", "lab1")],  # SELECT unreviewed tasks
        [],  # UPDATE ai_qc_status='pass'
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)
    # Verify ai_qc_status='pass' was set
    pass_updates = [sql for sql, _ in db.calls if "ai_qc_status = 'pass'" in sql]
    assert len(pass_updates) >= 1


def test_qc_fail_flags_labeller_and_qc_open_all(qc):
    m, db = qc
    m.gemini_check = lambda task: False
    db.results = [
        [("j1", 1, None)],  # AI row
        [(1,)],  # COUNT unreviewed
        [task_row("t1", "lab1")],  # SELECT unreviewed tasks
        [],  # UPDATE ai_qc_status='fail' for bad labeller tasks
        [],  # UPDATE ai_qc_status='fail' for gemini fail
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    qc_updates = [p for sql, p in db.calls if "qc_open" in sql]
    assert len(qc_updates) >= 1
    ai_update = [p for sql, p in db.calls if "UPDATE AI" in sql and "bad_labellers" in sql][0]
    assert ai_update == ('["lab1"]', "j1")


def test_qc_bad_labeller_skips_gemini_straight_to_qc_open(qc):
    m, db = qc
    reviewed = []
    m.gemini_check = lambda task: reviewed.append(task) or True
    db.results = [
        [("j1", 1, '["lab1"]')],  # AI row with bad_labellers
        [(1,)],  # COUNT unreviewed
        [task_row("t1", "lab1")],  # SELECT unreviewed tasks
        [],  # UPDATE ai_qc_status='fail' for bad labeller tasks
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    qc_updates = [p for sql, p in db.calls if "qc_open" in sql]
    assert len(qc_updates) >= 1
    assert reviewed == []


def test_qc_small_job_one_random_task_per_labeller(qc):
    m, db = qc
    reviewed = []
    m.gemini_check = lambda task: reviewed.append(task) or True
    db.results = [
        [("j1", 2, None)],  # AI row
        [(2,)],  # COUNT unreviewed
        [task_row("t1", "lab1"), task_row("t2", "lab1")],  # SELECT unreviewed tasks
        [],  # UPDATE ai_qc_status='pass' for reviewed
        [],  # UPDATE AI SET bad_labellers
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
        [("j1", 10, None)],  # AI row
        [(10,)],  # COUNT unreviewed
        rows,  # SELECT unreviewed tasks
        [],  # UPDATE ai_qc_status='pass' for each reviewed
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    assert any("ai_qc_status" in sql for sql, _ in db.calls)


def test_qc_large_job_dice_none_selected(qc, monkeypatch):
    m, db = qc
    m.QC_DICE_FIXED = 5
    monkeypatch.setattr("main.random.randint", lambda a, b: 4)
    m.gemini_check = lambda task: False
    rows = [task_row(f"t{i}", "lab1") for i in range(10)]
    db.results = [
        [("j1", 10, None)],  # AI row
        [(10,)],  # COUNT unreviewed
        rows,  # SELECT unreviewed tasks
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)


def test_qc_gemini_skipped_keeps_labelled(qc):
    m, db = qc
    m.gemini_check = lambda task: None
    db.results = [
        [("j1", 1, None)],  # AI row
        [(1,)],  # COUNT unreviewed
        [task_row("t1", "lab1")],  # SELECT unreviewed tasks
        [],  # UPDATE AI SET bad_labellers (no ai_qc_status change since verdict is None)
    ]

    m.run_aiqc()

    assert not any("qc_open" in sql for sql, _ in db.calls)
    # ai_qc_status should NOT be set to 'pass' or 'fail' since gemini returned None
    assert not any("ai_qc_status = 'pass'" in sql for sql, _ in db.calls)
    assert not any("ai_qc_status = 'fail'" in sql for sql, _ in db.calls)


# === ai_qc_status per-task tracking ===

def test_qc_only_samples_unreviewed_tasks(qc):
    m, db = qc
    reviewed = []
    m.gemini_check = lambda task: reviewed.append(task) or True
    db.results = [
        [("j1", 2, None)],  # AI row
        [(1,)],  # COUNT unreviewed (only 1, not 2)
        [task_row("t1", "lab1")],  # SELECT unreviewed tasks (only t1, t2 already has ai_qc_status='pass')
        [],  # UPDATE ai_qc_status='pass'
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    assert len(reviewed) == 1
    assert reviewed[0][0] == "t1"


def test_qc_fail_sets_ai_qc_status(qc):
    m, db = qc
    m.gemini_check = lambda task: False
    db.results = [
        [("j1", 1, None)],
        [(1,)],
        [task_row("t1", "lab1")],
        [],  # UPDATE ai_qc_status='fail' + qc_open
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    fail_updates = [sql for sql, _ in db.calls if "ai_qc_status = 'fail'" in sql]
    assert len(fail_updates) >= 1


def test_qc_gemini_none_keeps_status_null(qc):
    m, db = qc
    m.gemini_check = lambda task: None
    db.results = [
        [("j1", 1, None)],
        [(1,)],
        [task_row("t1", "lab1")],
        [],  # UPDATE AI SET bad_labellers
    ]

    m.run_aiqc()

    # No ai_qc_status should be set to 'pass' or 'fail' when gemini returns None
    assert not any("ai_qc_status = 'pass'" in sql for sql, _ in db.calls)
    assert not any("ai_qc_status = 'fail'" in sql for sql, _ in db.calls)


# === POST /humanqc ===

def test_humanqc_approve(client):
    tc, db = client

    resp = tc.post("/humanqc", json={"task_id": "t1", "action": "approve"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    sql, params = db.calls[0]
    assert "ai_qc_status = 'pass'" in sql
    assert params == ("t1",)
    assert db.commits == 1


def test_humanqc_relabel(client):
    tc, db = client

    resp = tc.post("/humanqc", json={"task_id": "t1", "action": "relabel"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    sql, params = db.calls[0]
    assert "qc_round = qc_round + 1" in sql
    assert "ai_qc_status = NULL" in sql
    assert params == ("t1",)
    assert db.commits == 1


# === GET /qc_tasks ===

def test_qc_tasks_returns_qc_open(client):
    tc, db = client
    qc_row = ("t1", "http://img", "c1", "j1", "lab1", "['cat1']", "cat1", "qc_open", None, None, "fail", 1)
    db.results.append([qc_row])

    resp = tc.get("/qc_tasks")

    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "t1"
    assert tasks[0]["status"] == "qc_open"
    assert tasks[0]["ai_qc_status"] == "fail"
    assert tasks[0]["qc_round"] == 1


def test_qc_tasks_empty_when_none(client):
    tc, db = client
    db.results.append([])

    resp = tc.get("/qc_tasks")

    assert resp.status_code == 200
    assert resp.json() == {"tasks": []}
