import os
import libsql
from fastapi import FastAPI
from pydantic import BaseModel
import uuid
import logging
import sys
from fastapi.middleware.cors import CORSMiddleware
from typing import cast
import time

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.INFO)


app = FastAPI()

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
        conn.execute("INSERT INTO Task (task_id, url, client_id, job_id, categories) VALUES (?, ?, ?, ?, ?)", 
                     (task_id, url, item.client_id, id, categories,))
        final_task_id_list.append(task_id)
    
    conn.execute("UPDATE Job SET task_id = ? WHERE job_id = ?", (str(final_task_id_list), id,))
    conn.commit()

@app.get("/task")
def get_task():
    task_obj: list[Task] = []  
    for item in conn.execute("SELECT * from Task WHERE locked IS NULL LIMIT 1").fetchall():
        task_obj.append(Task(item[0], item[1], item[2], item[3], item[4], item[5],item[6], item[7]))
    current_time = time.time()
    logger.info(task_obj)
    lock_task = conn.execute("UPDATE Task SET locked = ? WHERE task_id = ?", (current_time, str(task_obj[0].task_id)))
    conn.commit()
    logger.info(lock_task)
    return {"task": task_obj}

class UpdateLabel(BaseModel):
    task_id: str
    labeller_id: str
    label: list[str]

@app.post("/updatelabel")
def upd_label(task: UpdateLabel):
    conn.execute("UPDATE Task SET label = ?, labeller_id = ? WHERE task_id = ?", (str(task.label), task.labeller_id, task.task_id))
    conn.commit()
    return {"status": "success"}

class Task:
    def __init__(self, task_id, url, client_id, job_id, labeller_id, label, categories, locked):
        self.task_id = task_id
        self.url = url
        self.client_id = client_id
        self.job_id = job_id
        self.labeller_id = labeller_id
        self.label= label
        self.categories= categories
        self.locked= locked