"""End-to-end tests: real uvicorn server on SQLite (tmp dir), Gemini mocked via
GEMINI_MOCK_VERDICT, frontend driven by Playwright.

Run: uv run --extra dev pytest tests/test_e2e.py -v
(requires: playwright install chromium)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import libsql
import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent
BASE = "http://localhost:8000"  # hardcoded in the HTML pages' API_BASE


@pytest.fixture
def server(request, tmp_path):
    """Launch uvicorn with cwd=tmp_path so its local data-labeller.db is isolated,
    and GEMINI_MOCK_VERDICT set to the parametrized PASS/FAIL."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TURSO_")}
    env["GEMINI_MOCK_VERDICT"] = getattr(request, "param", "PASS")
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", "8000"],
        cwd=tmp_path, env=env,
    )
    for _ in range(100):
        try:
            if httpx.get(f"{BASE}/").status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield tmp_path / "data-labeller.db"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def seed(n=2):
    r = httpx.post(f"{BASE}/createjob", json={
        "savedCats": ["strawberry", "window"],
        "savedUrls": [f"http://example.com/img{i}.png" for i in range(n)],
        "client_id": "client1",
    })
    assert r.status_code == 200


def label_all_via_ui(page, n):
    """Enter name and submit labels for n tasks through labeller.html."""
    page.goto((FRONTEND / "labeller.html").as_uri())
    page.fill("#name-input", "Vy")
    page.click("#name-screen button")
    for _ in range(n):
        page.wait_for_selector("#cat-0")
        page.check("#cat-0")
        page.click("#submit-btn")


def db_rows(db_file, sql):
    return libsql.connect(str(db_file)).execute(sql).fetchall()


@pytest.mark.parametrize("server", ["PASS"], indirect=True)
def test_aiqc_pass(server, page):
    seed(2)
    label_all_via_ui(page, 2)

    page.goto((FRONTEND / "qc.html").as_uri())
    page.click("text=Run AI QC")
    expect(page.get_by_text("No tasks need QC right now.")).to_be_visible()

    # Small job (<10 tasks): one random task per labeller is reviewed
    rows = db_rows(server, "SELECT ai_qc_status, status FROM Task")
    assert sorted(rows, key=str) == [("pass", "labelled"), (None, "labelled")], rows
    assert db_rows(server, "SELECT bad_labellers FROM AI") == [("[]",)]


@pytest.mark.parametrize("server", ["FAIL"], indirect=True)
def test_aiqc_fail_then_human_qc(server, page):
    seed(2)
    label_all_via_ui(page, 2)

    page.goto((FRONTEND / "qc.html").as_uri())
    page.click("text=Run AI QC")
    expect(page.get_by_text("task(s) need review")).to_be_visible()
    assert page.text_content("#queue-count") == "2"
    assert db_rows(server, "SELECT ai_qc_status, status FROM Task") == \
        [("fail", "qc_open"), ("fail", "qc_open")]

    for _ in range(2):  # approve both flagged tasks
        page.wait_for_selector("#approve-btn:not([disabled])")
        page.click("#approve-btn")
    expect(page.get_by_text("No tasks need QC right now.")).to_be_visible()

    assert db_rows(server, "SELECT status FROM Task") == [("labelled",), ("labelled",)]


# === Edge cases ===


def test_empty_name_alert_and_no_tasks(server, page):
    dialogs = []
    page.on("dialog", lambda d: dialogs.append(d.message) or d.dismiss())
    page.goto((FRONTEND / "labeller.html").as_uri())
    page.click("#name-screen button")  # no name entered
    assert dialogs == ["Please enter your name."]

    page.fill("#name-input", "Vy")
    page.click("#name-screen button")
    expect(page.get_by_text("No tasks available right now.")).to_be_visible()


@pytest.mark.parametrize("server", ["PASS"], indirect=True)
def test_multi_label_with_free_text(server, page):
    seed(1)
    page.goto((FRONTEND / "labeller.html").as_uri())
    page.fill("#name-input", "Vy")
    page.click("#name-screen button")
    page.wait_for_selector("#cat-0")
    page.check("#cat-0")
    page.check("#cat-1")
    page.fill("#label", "extra note")
    page.click("#submit-btn")
    expect(page.get_by_text("No tasks available right now.")).to_be_visible()

    rows = db_rows(server, "SELECT label FROM Task")
    assert rows == [("['strawberry', 'window', 'extra note']",)]


@pytest.mark.parametrize("server", ["ERROR"], indirect=True)
def test_gemini_error_leaves_task_unreviewed(server, page):
    seed(2)
    label_all_via_ui(page, 2)

    httpx.post(f"{BASE}/run-qc")  # verdict None: task must be retried next pass
    rows = db_rows(server, "SELECT ai_qc_status, status FROM Task")
    assert all(r == (None, "labelled") for r in rows), rows
    assert db_rows(server, "SELECT bad_labellers FROM AI") == [("[]",)]


@pytest.mark.parametrize("server", ["FAIL"], indirect=True)
def test_relabel_round_trip(server, page):
    seed(1)
    label_all_via_ui(page, 1)

    page.goto((FRONTEND / "qc.html").as_uri())
    page.click("text=Run AI QC")
    page.wait_for_selector("#relabel-btn:not([disabled])")
    page.click("#relabel-btn")
    expect(page.get_by_text("No tasks need QC right now.")).to_be_visible()
    assert db_rows(server, "SELECT status, labeller_id, ai_qc_status, qc_round FROM Task") == \
        [("open", None, None, 1)]

    # stored name in localStorage: labeller resumes without the name screen
    page.goto((FRONTEND / "labeller.html").as_uri())
    page.wait_for_selector("#cat-0")
    page.check("#cat-0")
    page.click("#submit-btn")
    expect(page.get_by_text("No tasks available right now.")).to_be_visible()
    assert db_rows(server, "SELECT status, qc_round FROM Task") == [("labelled", 1)]


@pytest.mark.parametrize("server", ["PASS"], indirect=True)
def test_resume_in_progress_task_after_reload(server, page):
    seed(2)
    page.goto((FRONTEND / "labeller.html").as_uri())
    page.fill("#name-input", "Vy")
    page.click("#name-screen button")
    page.wait_for_selector("#cat-0")  # task claimed, not submitted

    page.reload()  # must resume the same 'labelling' task
    page.wait_for_selector("#cat-0")
    assert db_rows(server, "SELECT status FROM Task") == \
        [("labelling",), ("open",)]


@pytest.mark.parametrize("server", ["PASS"], indirect=True)
def test_stale_locked_task_reset(server):
    seed(2)
    r = httpx.get(f"{BASE}/task", params={"labeller_id": "Vy"})
    task_id = r.json()["task"][0]["task_id"]

    db = libsql.connect(str(server))
    db.execute("UPDATE Task SET locked_at = '2000-01-01T00:00:00' WHERE task_id = ?", (task_id,))
    db.commit()

    # stale reset runs first and frees the abandoned task, so Vy's stale claim
    # is handed to Other instead of serving the second task
    other_id = httpx.get(f"{BASE}/task", params={"labeller_id": "Other"}).json()["task"][0]["task_id"]
    assert other_id == task_id
