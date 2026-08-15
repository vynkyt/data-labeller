# Data Labeller

Welcome to *Data Labeller*!

An AI-assisted media annotation pipeline for images, videos, and audio datasets. Built with Python/FastAPI, Turso (libSQL), Gemini, and vanilla HTML/Tailwind CSS.

---
# How It Works

Data Labeller is a four-stage pipeline for annotating media datasets:

1. **Admin** — Create jobs by uploading media URLs and defining category lists
2. **Labeller** — Annotate media tasks with category labels and free-text descriptions
3. **AI QC** — Automated quality control using Gemini to sample and verify labels
4. **Human QC** — Review flagged labels, approve correct ones or send back for relabelling

Tasks flow through each stage automatically. If a labeller's labels are flagged by AI QC, a human reviewer decides whether to approve or send the task back for relabelling — with a round counter tracking how many times a task has bounced back.

---
# Development Process

## Foundation

Started with a single `labeller.html` page and a FastAPI backend. The original goal was simple: let someone enter their name, get a media task, label it, and submit. From there it snowballed into a full pipeline with admin job creation, automated AI quality control, and a human QC review stage.

## Architecture

The whole thing is intentionally over-engineered for what it does:

- **Frontend**: Four standalone HTML files (`index.html`, `admin.html`, `labeller.html`, `qc.html`) — no build system, no framework, no bundler. Just Tailwind via CDN and vanilla JS.
- **Backend**: Single Python file (`main.py`) with FastAPI. One file does everything — endpoints, scheduler, AI QC, database migrations.
- **Database**: Turso (libSQL) — serverless SQLite. Handles tasks, jobs, labels, QC status, and per-task AI QC tracking.
- **AI QC**: Gemini reviews a sample of labels per job. Small jobs (<10 tasks): one random task per labeller. Large jobs: ~10% dice-rolled. Failing a single task flags the entire labeller's work in that job.

## Key Design Decisions

1. **Per-task AI QC tracking**: Each task has its own `ai_qc_status` (pass/fail/null) so relabelled tasks get re-reviewed without redundantly checking ones that already passed.
2. **Staleness reset**: Tasks stuck in "labelling" for >30 minutes get reset to "open" so they don't disappear if a labeller closes their browser.
3. **Session persistence**: Labeller name stored in localStorage so refreshing doesn't lose your in-progress task.
4. **QC round tracking**: `qc_round` counter on each task tracks how many times it's been sent back for relabelling.

## Miscellaneous Challenges

---

# Tech Stack

- Python / FastAPI
- Turso (libSQL)
- Google Gemini (AI QC)
- HTML / Tailwind CSS / Vanilla JS
- APScheduler (background QC runs)

## Tools

- Visual Studio Code
- uv (Python package manager)

## Hosting

- Local development (`uvicorn --reload`)
---

# Key Features

- Four-role pipeline: Admin, Labeller, AI QC, Human QC
- Automated quality control with Gemini sampling and per-task tracking
- Human QC review with approve/relabel actions and round-trip tracking
- Session persistence — labellers resume where they left off on refresh
- Stale task recovery — labelling tasks auto-reset after 30 minutes
- Three standalone HTML pages + landing page, no build step required
---

# Guide to Data Labeller

Open `index.html` in a browser to access the landing page, then pick your role:

- **Admin** (`admin.html`) — Enter media URLs and category lists, then submit to create a labelling job
- **Labeller** (`labeller.html`) — Enter your name, get assigned a task, label it with categories and descriptions, submit. Refreshing won't lose your work.
- **QC Reviewer** (`qc.html`) — See tasks flagged by AI QC, review the media and submitted labels, approve or send back to the labeller queue
