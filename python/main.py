import os
import json
import random
import libsql
from fastapi import FastAPI
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

def migrate():
    for stmt in (
        "ALTER TABLE AI ADD COLUMN ai_processed INTEGER DEFAULT 0",
        "ALTER TABLE AI ADD COLUMN bad_labellers TEXT",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()

def gemini_check(task):
    _, url, _, job_id, labeller_id, label, categories, _, _ = task
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
    ai_rows = conn.execute("SELECT job_id, total_tasks, ai_processed, bad_labellers FROM AI").fetchall()
    for job_id, total_tasks, ai_processed, bad_raw in ai_rows:
        if ai_processed:
            continue
        if total_tasks == 0:
            conn.execute("UPDATE AI SET ai_processed = 1 WHERE job_id = ?", (job_id,))
            conn.commit()
            continue

        labelled = conn.execute("SELECT COUNT(*) FROM Task WHERE status = 'labelled' AND job_id = ?", (job_id,)).fetchall()
        if not labelled or labelled[0][0] != total_tasks:
            continue

        tasks = conn.execute("SELECT * FROM Task WHERE job_id = ?", (job_id,)).fetchall()
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

        for t in tasks:
            if t[4] in bad_labellers and t[8] != "qc_open":
                conn.execute("UPDATE Task SET status = 'qc_open' WHERE task_id = ?", (t[0],))

        for t in reviewed:
            verdict = gemini_check(t)
            if verdict is False:
                logger.info(f"AI QC flagged labeller {t[4]} in job {job_id}")
                bad_labellers.append(t[4])
                conn.execute("UPDATE Task SET status = 'qc_open' WHERE job_id = ? AND labeller_id = ?", (job_id, t[4]))

        conn.execute(
            "UPDATE AI SET ai_processed = 1, bad_labellers = ? WHERE job_id = ?",
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

conn = libsql.connect(
        database=os.environ["TURSO_DATABASE_URL"],
        auth_token=os.environ["TURSO_AUTH_TOKEN"],
    )

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

@app.get("/task")
def get_task():
    task_obj: list[Task] = []  
    for item in conn.execute("SELECT * from Task WHERE status = 'open' LIMIT 1").fetchall():
        task_obj.append(Task(item[0], item[1], item[2], item[3], item[4], item[5],item[6], item[7], item[8]))

    if not task_obj:
        return {"message": "there are no open tasks"}

    conn.execute("UPDATE Task SET status = 'labelling' WHERE task_id = ?", [str(task_obj[0].task_id)])
    conn.commit()
    logger.info(str(task_obj[0].task_id))
    return {"task": task_obj}

class UpdateLabel(BaseModel):
    task_id: str
    labeller_id: str
    label: list[str]

@app.post("/updatelabel")
def upd_label(task: UpdateLabel):
    conn.execute("UPDATE Task SET status = 'labelled', label = ?, labeller_id = ? WHERE task_id = ?", (str(task.label), task.labeller_id, task.task_id))
    conn.commit()
    return {"status": "success"}

class Task:
    def __init__(self, task_id, url, client_id, job_id, labeller_id, label, categories, status, qc_label):
        self.task_id = task_id
        self.url = url
        self.client_id = client_id
        self.job_id = job_id
        self.labeller_id = labeller_id
        self.label= label
        self.categories= categories
        self.status= status
        self.qc_label = qc_label

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
