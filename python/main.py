import os
import json
import random
import libsql
from fastapi import FastAPI, Query
from pydantic import BaseModel
import uuid
import logging
import sys
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import cast
import time

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.INFO)

QC_DICE_FIXED = random.randint(0, 9)
STALE_LABELLING_SECONDS = 30 * 60  # 30 minutes

def migrate():
    for stmt in (
        "CREATE TABLE IF NOT EXISTS Job (job_id TEXT PRIMARY KEY, task_id TEXT)",
        "CREATE TABLE IF NOT EXISTS Task ("
        "task_id TEXT PRIMARY KEY, url TEXT, client_id TEXT, job_id TEXT, "
        "labeller_id TEXT, label TEXT, categories TEXT, status TEXT, "
        "qc_label TEXT, locked_at TEXT, ai_qc_status TEXT DEFAULT NULL, "
        "qc_round INTEGER DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS AI ("
        "job_id TEXT PRIMARY KEY, total_tasks INTEGER, "
        "ai_processed INTEGER DEFAULT 0, bad_labellers TEXT)",
        "ALTER TABLE AI ADD COLUMN ai_processed INTEGER DEFAULT 0",
        "ALTER TABLE AI ADD COLUMN bad_labellers TEXT",
        "ALTER TABLE Task ADD COLUMN locked_at TEXT",
        "ALTER TABLE Task ADD COLUMN ai_qc_status TEXT DEFAULT NULL",
        "ALTER TABLE Task ADD COLUMN qc_round INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()

def gemini_check(task):
    _, url, _, job_id, labeller_id, label, categories, _, _, _, _, _ = task
    logger.info(f"AI QC reviewing task in job {job_id} by labeller {labeller_id}: {label}")
    try:
        from google import genai
    except ImportError:
        logger.error("google-genai not installed; skipping AI review")
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set; skipping AI review")
        return None
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = (
        f"You are an AI quality checker for a data labelling pipeline.\n"
        f"Media url: {url}\n"
        f"Allowed categories: {categories}\n"
        f"Labeller's chosen label: {label}\n"
        "Decide whether the chosen label is a correct/plausible category for the media.\n"
        'Reply with exactly "PASS" or "FAIL".'
    )
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        text = resp.text.strip().upper()
        logger.info(f"AI QC verdict: {text}")
        return text.startswith("PASS")
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None

def run_aiqc():
    logger.info("Running AI QC pass")
    ai_rows = conn.execute("SELECT job_id, total_tasks, bad_labellers FROM AI").fetchall()
    for job_id, total_tasks, bad_raw in ai_rows:
        if total_tasks == 0:
            continue

        # Only consider labelled tasks that haven't been AI QC'd yet
        unreviewed = conn.execute(
            "SELECT COUNT(*) FROM Task WHERE status = 'labelled' AND ai_qc_status IS NULL AND job_id = ?",
            (job_id,)
        ).fetchall()
        if not unreviewed or unreviewed[0][0] == 0:
            continue

        tasks = conn.execute(
            "SELECT * FROM Task WHERE status = 'labelled' AND ai_qc_status IS NULL AND job_id = ?",
            (job_id,)
        ).fetchall()
        bad_labellers = json.loads(bad_raw) if bad_raw else []
        reviewed = []

        if total_tasks < 10:
            by_labeller: dict = {}
            for t in tasks:
                by_labeller.setdefault(t[4], []).append(t)
            for lab, ts in by_labeller.items():
                if lab not in bad_labellers and ts:
                    reviewed.append(random.choice(ts))
        else:
            for t in tasks:
                if random.randint(0, 999999) % 10 == QC_DICE_FIXED:
                    reviewed.append(t)

        # Flag bad labellers' unreviewed tasks
        for t in tasks:
            if t[4] in bad_labellers:
                conn.execute(
                    "UPDATE Task SET status = 'qc_open', ai_qc_status = 'fail' WHERE task_id = ? AND ai_qc_status IS NULL",
                    (t[0],)
                )

        # Gemini review
        for t in reviewed:
            verdict = gemini_check(t)
            if verdict is False:
                logger.info(f"AI QC flagged labeller {t[4]} in job {job_id}")
                bad_labellers.append(t[4])
                conn.execute(
                    "UPDATE Task SET status = 'qc_open', ai_qc_status = 'fail' WHERE job_id = ? AND labeller_id = ? AND ai_qc_status IS NULL",
                    (job_id, t[4])
                )
            elif verdict is True:
                conn.execute(
                    "UPDATE Task SET ai_qc_status = 'pass' WHERE task_id = ?",
                    (t[0],)
                )
            # verdict is None (API error) — leave ai_qc_status as NULL, retry next pass

        conn.execute(
            "UPDATE AI SET bad_labellers = ? WHERE job_id = ?",
            (json.dumps(list(set(bad_labellers))), job_id),
        )
        conn.commit()

def task():
    logger.info("scheduler tick")
    run_aiqc()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply schema migrations
    migrate()

    # Initialize the scheduler
    scheduler = AsyncIOScheduler()
    
    # Add an interval job (runs every 5 seconds)
    scheduler.add_job(task, "interval", seconds=600)
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started.")
    
    yield  # The FastAPI application runs while paused here
    
    # Shutdown the scheduler cleanly when the app stops
    scheduler.shutdown()
    logger.info("Scheduler stopped.")

app = FastAPI(lifespan=lifespan)

# origins = [
#     "file:///C:/Users/User/OneDrive/Desktop/data-labeller/admin.html",
# ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

if TURSO_URL and TURSO_TOKEN:
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
else:
    logger.info("No Turso credentials found — using local SQLite (data-labeller.db)")
    conn = libsql.connect("data-labeller.db")

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}

@app.get("/hitdatabase")
def hit_fake_db():
    conn.execute("INSERT INTO users (name) VALUES (?)", ("Frenchie",))
    conn.commit()
    rows = conn.execute("SELECT * FROM users").fetchall()
    print(rows)

# class Task(BaseModel):
#     task_id: str
#     url: str
#     client_id: str
#     job_id: str
#     labeller_id: str
#     label: list[str]
#     categories: str
#     locked: bool

class Job(BaseModel):
    # job_id: str
    # tasks: list[Task]
    # completed_at: str
    savedCats: list[str]
    savedUrls: list[str]
    client_id: str

@app.post("/createjob")
def hit_job(item: Job):
    id = str(uuid.uuid4())
    conn.execute("INSERT INTO Job (job_id) VALUES (?)", (id,))
    final_task_id_list = []

    categories = ", ".join(item.savedCats)
    logging.info(categories)

    for url in item.savedUrls:
        task_id = str(uuid.uuid4())
        conn.execute("INSERT INTO Task (task_id, url, client_id, job_id, categories, status) VALUES (?, ?, ?, ?, ?, ?)", 
                     (task_id, url, item.client_id, id, categories, 'open'))
        final_task_id_list.append(task_id)
    
    conn.execute("INSERT INTO AI (job_id, total_tasks) VALUES (?, ?)", (id, len(final_task_id_list)))
    conn.execute("UPDATE Job SET task_id = ? WHERE job_id = ?", (str(final_task_id_list), id,))
    conn.commit()

def reset_stale_labelling_tasks():
    """Reset tasks stuck in 'labelling' for longer than the staleness threshold back to 'open'.

    Uses the locked_at timestamp column to determine staleness.
    """
    try:
        cutoff_epoch = time.time() - STALE_LABELLING_SECONDS
        # Convert epoch cutoff to ISO format for comparison with locked_at text
        cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cutoff_epoch))
        conn.execute(
            "UPDATE Task SET status = 'open', labeller_id = NULL, locked_at = NULL "
            "WHERE status = 'labelling' AND locked_at IS NOT NULL AND locked_at < ?",
            (cutoff_iso,),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Staleness reset failed: {e}")


@app.get("/task")
def get_task(labeller_id: str | None = None):
    # Always reset stale tasks first
    reset_stale_labelling_tasks()

    # If a labeller_id is provided, check for an in-progress task first
    if labeller_id:
        rows = conn.execute(
            "SELECT * FROM Task WHERE status = 'labelling' AND labeller_id = ? LIMIT 1",
            (labeller_id,),
        ).fetchall()
        if rows:
            task_obj = Task(*rows[0])
            logger.info(f"Resuming task {task_obj.task_id} for labeller {labeller_id}")
            return {"task": [task_obj]}

    # No in-progress task (or no labeller_id) — fetch next open task
    task_obj: list[Task] = []
    for item in conn.execute("SELECT * FROM Task WHERE status = 'open' LIMIT 1").fetchall():
        task_obj.append(Task(*item))

    if not task_obj:
        return {"message": "there are no open tasks"}

    update_sql = "UPDATE Task SET status = 'labelling', locked_at = ?"
    update_params: list = [time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), task_obj[0].task_id]

    if labeller_id:
        update_sql += ", labeller_id = ?"
        update_params.append(labeller_id)

    update_sql += " WHERE task_id = ?"
    conn.execute(update_sql, update_params)
    conn.commit()
    logger.info(f"Fetched task {task_obj[0].task_id} for labeller {labeller_id}")
    return {"task": task_obj}

class UpdateLabel(BaseModel):
    task_id: str
    labeller_id: str
    label: list[str]

@app.post("/updatelabel")
def upd_label(task: UpdateLabel):
    conn.execute("UPDATE Task SET status = 'labelled', label = ?, labeller_id = ?, locked_at = NULL WHERE task_id = ?", (str(task.label), task.labeller_id, task.task_id))
    conn.commit()
    return {"status": "success"}

class Task:
    def __init__(self, task_id, url, client_id, job_id, labeller_id, label, categories, status, qc_label, locked_at=None, ai_qc_status=None, qc_round=0):
        self.task_id = task_id
        self.url = url
        self.client_id = client_id
        self.job_id = job_id
        self.labeller_id = labeller_id
        self.label = label
        self.categories = categories
        self.status = status
        self.qc_label = qc_label
        self.locked_at = locked_at
        self.ai_qc_status = ai_qc_status
        self.qc_round = qc_round

@app.get("/countlabelled")
def countlabelled():
    job_ids = conn.execute("SELECT job_id from AI").fetchall()
    logger.info(job_ids)
    for i in job_ids:
        labelled_task_count = conn.execute(f"SELECT COUNT(*) from Task WHERE status = 'labelled' AND job_id = '{str(i[0])}'").fetchall()
        total_tasks = conn.execute(f"SELECT total_tasks from AI where job_id = '{str(i[0])}'").fetchall()
        logger.info(f"id {str(i[0])} with task count:  {total_tasks}")
        if labelled_task_count == total_tasks:
            labelled_tasks = conn.execute(f"SELECT * from Task WHERE job_id = '{str(i[0])}'").fetchall()
            logger.info(labelled_tasks)
            return labelled_tasks
    conn.commit()


class HumanQC(BaseModel):
    task_id: str
    action: str  # "approve" or "relabel"

@app.post("/humanqc")
def human_qc(request: HumanQC):
    if request.action == "approve":
        conn.execute(
            "UPDATE Task SET status = 'labelled', ai_qc_status = 'pass' WHERE task_id = ?",
            (request.task_id,),
        )
    elif request.action == "relabel":
        conn.execute(
            "UPDATE Task SET status = 'open', labeller_id = NULL, locked_at = NULL, "
            "ai_qc_status = NULL, qc_round = qc_round + 1 WHERE task_id = ?",
            (request.task_id,),
        )
    conn.commit()
    return {"status": "success"}


@app.get("/qc_tasks")
def get_qc_tasks():
    tasks = conn.execute("SELECT * FROM Task WHERE status = 'qc_open'").fetchall()
    return {"tasks": [Task(*t) for t in tasks]}
