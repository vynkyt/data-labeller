# Data Labeller

Welcome to *Data Labeller*!

An AI-assisted media annotation pipeline for images, videos, and audio datasets. Built with Python/FastAPI, Turso (libSQL), Gemini, and vanilla HTML/Tailwind CSS.

---

# How It Works

Data Labeller is a four-stage pipeline for annotating media datasets:

1. **Admin**: Create jobs by uploading media URLs and defining category lists
2. **Labeller**: Annotate media tasks with category labels and free-text descriptions
3. **AI QC**: Automated quality control using Gemini to sample and verify labels. Gemini reviews a sample of labels per job. Small jobs (<10 tasks): one random task per labeller. Large jobs: ~10% dice-rolled. Failing a single task flags the entire labeller's work in that job.
4. **Human QC**: Review flagged labels, approve correct ones or send back for relabelling by setting task status back to "open".
---

# Development Process

  

## Foundation

  

## Miscellaneous Challenges

   
   for human qc, idk if i want qc to relabel if the labels dont match, or send the tasks back to labellers. im leaning more towards sending taks back to labellers, but then i dont know what to set the status to. i contemplated having qc-checking and qc-checked, but then that would mean the task ending point is no longer "labelled", and there would be no sure way to determine which tasks are truly ready. 
   
   I decided to keep "labelled" as the ending point and to add a new column "qc_round", which counts the number of times a task has gone through human QC. 


   if its set back to "open", it goes through the pipeline again but theres a guardrail on ai reviewing the same jobs, meaning these tasks may never get reviewed. 
   
   So I decided on per-task AI QC checking by setting three statuses for AI QC, *null*/*pass*/*fail*, and tasks that go through the pipeline again after human QC has AI QC reset to *null*.

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
- Session persistence: labellers resume where they left off on refresh
- Stale task recovery: labelling tasks auto-reset after 30 minutes

---

# Guide to Data Labeller

## Quick Start (no accounts needed)

```bash
cd python
uv sync
uv run uvicorn main:app --reload --reload-dir .
```

This runs the app with a local SQLite database (`data-labeller.db`) with no configuration needed!
## With Turso / Gemini (optional)

If you want to use Turso for the database and/or Gemini for AI quality control:

1. Copy the example env file and fill in your credentials:

   ```bash
   cp ../.env.example .env
   ```

2. Run with the env file loaded:

   ```bash
   uv run --env-file .env uvicorn main:app --reload --reload-dir .
   ``` 

## Load Demo Data

In a separate terminal:

```bash
uv run python seed.py
```

This creates a sample job with 6 public images and 4 categories. Tasks appear immediately in the labeller page.
## Open the UI

Open `index.html` (in the project root) in a browser to access the landing page, then pick a role:
- **Admin**: creates jobs with media URLs and categories
- **Labeller**: annotates media tasks
- **QC Reviewer**: reviews AI-flagged labels
## Environment Variables

Copy `.env.example` to `.env` and fill in as needed. The variables are all optional, and their functionalities are listed below: 

- `TURSO_DATABASE_URL`: Turso DB connection string. Without it, uses local SQLite.
- `TURSO_AUTH_TOKEN`: Turso auth token. Without it, uses local SQLite.
- `GEMINI_API_KEY`: Google Gemini API key. Without it, AI QC is skipped.
- `GEMINI_MODEL`: Gemini model name. Defaults to `gemini-2.5-flash`.
## Running Tests

```bash
uv run pytest tests/ -v
```