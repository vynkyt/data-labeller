import re
import pytest
from fastapi.testclient import TestClient

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@pytest.fixture
def client(db):
    from unittest.mock import patch
    with patch("main.conn", db):
        from main import app
        yield TestClient(app), db


# === /createjob ===

def test_createjob_1_url_1_cat(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["cat1"], "savedUrls": ["http://img"], "client_id": "c1"
    })
    assert resp.status_code == 200

    jobs = db.execute("SELECT job_id FROM Job").fetchall()
    assert len(jobs) == 1
    job_id = jobs[0][0]
    assert UUID_RE.match(job_id)

    tasks = db.execute("SELECT task_id, url, client_id, categories, status FROM Task").fetchall()
    assert len(tasks) == 1
    tid, url, cid, cats, status = tasks[0]
    assert UUID_RE.match(tid)
    assert url == "http://img"
    assert cid == "c1"
    assert cats == "cat1"
    assert status == "open"

    ai = db.execute("SELECT job_id, total_tasks FROM AI").fetchall()
    assert len(ai) == 1
    assert ai[0][0] == job_id
    assert ai[0][1] == 1

    job_task_ids = db.execute("SELECT task_id FROM Job WHERE job_id = ?", (job_id,)).fetchall()
    assert tid in str(job_task_ids)


def test_createjob_multiple_urls(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["a", "b"], "savedUrls": ["u1", "u2", "u3"], "client_id": "c1"
    })
    assert resp.status_code == 200

    tasks = db.execute("SELECT url, categories FROM Task ORDER BY rowid").fetchall()
    assert len(tasks) == 3
    assert [t[0] for t in tasks] == ["u1", "u2", "u3"]
    assert all(t[1] == "a, b" for t in tasks)

    ai = db.execute("SELECT total_tasks FROM AI").fetchall()
    assert ai[0][0] == 3


def test_createjob_empty_urls(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["a"], "savedUrls": [], "client_id": "c1"
    })
    assert resp.status_code == 200
    assert db.execute("SELECT * FROM Task").fetchall() == []
    assert db.execute("SELECT total_tasks FROM AI").fetchall()[0][0] == 0


def test_createjob_empty_cats(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": [], "savedUrls": ["u"], "client_id": "c1"
    })
    assert resp.status_code == 200
    cats = db.execute("SELECT categories FROM Task").fetchall()[0][0]
    assert cats == ""


def test_createjob_comma_in_cats(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["a,b", "c"], "savedUrls": ["u"], "client_id": "c1"
    })
    assert resp.status_code == 200
    cats = db.execute("SELECT categories FROM Task").fetchall()[0][0]
    assert cats == "a,b, c"


def test_createjob_duplicate_urls(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["a"], "savedUrls": ["u", "u"], "client_id": "c1"
    })
    assert resp.status_code == 200
    tasks = db.execute("SELECT url FROM Task").fetchall()
    assert len(tasks) == 2
    assert tasks[0][0] == tasks[1][0]

    ids = db.execute("SELECT task_id FROM Task").fetchall()
    assert ids[0][0] != ids[1][0]


def test_createjob_task_ids_stored_on_job(client):
    tc, db = client
    resp = tc.post("/createjob", json={
        "savedCats": ["a"], "savedUrls": ["u1", "u2"], "client_id": "c1"
    })
    assert resp.status_code == 200
    task_ids = [r[0] for r in db.execute("SELECT task_id FROM Task").fetchall()]
    job_row = db.execute("SELECT task_id FROM Job").fetchall()[0][0]
    for tid in task_ids:
        assert tid in job_row


# === /countlabelled ===

def test_countlabelled_no_jobs(client):
    tc, db = client
    resp = tc.get("/countlabelled")
    assert resp.status_code == 200


def test_countlabelled_all_labelled(client):
    tc, db = client
    db.execute("INSERT INTO Job (job_id) VALUES (?)", ("j1",))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t1", "u1", "c1", "j1", "labelled"))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t2", "u2", "c1", "j1", "labelled"))
    db.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", ("j1", 2))
    db.commit()

    resp = tc.get("/countlabelled")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_countlabelled_none_labelled(client):
    tc, db = client
    db.execute("INSERT INTO Job (job_id) VALUES (?)", ("j1",))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t1", "u1", "c1", "j1", "open"))
    db.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", ("j1", 1))
    db.commit()

    resp = tc.get("/countlabelled")
    assert resp.status_code == 200
    assert resp.json() is None


def test_countlabelled_partial(client):
    tc, db = client
    db.execute("INSERT INTO Job (job_id) VALUES (?)", ("j1",))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t1", "u1", "c1", "j1", "labelled"))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t2", "u2", "c1", "j1", "open"))
    db.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", ("j1", 2))
    db.commit()

    resp = tc.get("/countlabelled")
    assert resp.status_code == 200
    assert resp.json() is None


def test_countlabelled_multi_jobs_first_complete(client):
    tc, db = client
    db.execute("INSERT INTO Job (job_id) VALUES (?)", ("j1",))
    db.execute("INSERT INTO Job (job_id) VALUES (?)", ("j2",))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t1", "u1", "c1", "j1", "labelled"))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t2", "u2", "c1", "j1", "labelled"))
    db.execute("INSERT INTO Task (task_id, url, client_id, job_id, status) VALUES (?, ?, ?, ?, ?)",
               ("t3", "u3", "c1", "j2", "open"))
    db.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", ("j1", 2))
    db.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", ("j2", 1))
    db.commit()

    resp = tc.get("/countlabelled")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(t[3] == "j1" for t in data)
