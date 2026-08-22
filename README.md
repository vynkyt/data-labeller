# Data Labeller

Welcome to *Data Labeller*!

<div style="text-align:center;">
<img width="1779" height="1158" alt="image" src="https://github.com/user-attachments/assets/912deab5-3617-4dbc-8460-8faf622780d9" />
</div>
<br>

A media annotation pipeline for images, videos, and audio datasets, with automated quality control using AI. Built with Python/FastAPI, Turso (libSQL), Gemini, and vanilla HTML/Tailwind CSS.

---

# How It Works

Data Labeller is a four-stage pipeline for annotating media datasets:

1. **Admin**: Create jobs by uploading media URLs and defining category lists.
2. **Labeller**: Annotate media tasks with category labels and free-text descriptions.
3. **AI QC**: Automated quality control using Gemini to sample and verify labels. Gemini reviews a sample of labels per job:

   * Small jobs (<10 tasks): one random task per labeller.
   * Large jobs: roughly 10% of tasks are randomly sampled.
   * If a sampled task fails, the entire labeller's work for that job is flagged for human review.
4. **Human QC**: Review flagged labels, approve correct ones, or send them back for relabelling by setting the task status back to `open`.

---

# Key Features

Besides the four-role pipeline, other features include:

* **Session persistence**: labellers can resume where they left off after refreshing
* **Stale task recovery**: labelling tasks auto-reset after 30 minutes
* Local SQLite database with no configuration needed
* Optional Turso database and Gemini AI QC

---

# Tech Stack

* Python / FastAPI
* Turso (libSQL)
* Google Gemini (AI QC)
* HTML / Tailwind CSS / Vanilla JS
* APScheduler (background QC runs)

## Tools

* Visual Studio Code
* uv (Python package manager)

---

# Guide to Data Labeller

## Try the UI

View the UI <a href="https://data-labeller-three.vercel.app/" target="_blank">here</a>. Some functions such as retrieving tasks to label or check are not available unless you start up the backend (see below!).

## Quick Start

No accounts or configuration are needed to run the app locally.

```bash
cd python
uv sync
uv run uvicorn main:app --reload --reload-dir .
```

This runs the app with a local SQLite database (`data-labeller.db`).

## Load Demo Data

In a separate terminal:

```bash
uv run python seed.py
```

This creates a sample job with 6 public images and 4 categories. Tasks appear immediately on the labeller page.

## Open the UI

Open `index.html` in the project root in a browser to access the landing page, then pick a role:

* **Admin**: creates jobs with media URLs and categories
* **Labeller**: annotates media tasks
* **QC Reviewer**: reviews AI-flagged labels

---

# Turso / Gemini

If you want to use Turso for the database and/or Gemini for AI quality control:

1. Copy the example env file and fill in your credentials:

```bash
cp ../.env.example .env
```

2. Run with the env file loaded:

```bash
uv run --env-file .env uvicorn main:app --reload --reload-dir .
```

## Environment Variables

Copy `.env.example` to `.env` and fill in as needed. All variables are optional:

* `TURSO_DATABASE_URL`: Turso DB connection string. Without it, the app uses local SQLite.
* `TURSO_AUTH_TOKEN`: Turso auth token. Without it, the app uses local SQLite.
* `GEMINI_API_KEY`: Google Gemini API key. Without it, AI QC is skipped.
* `GEMINI_MODEL`: Gemini model name. Defaults to `gemini-2.5-flash`.

---

# Running Tests

## Unit Tests

Unit tests don't require a server or browser:

```bash
uv run --extra dev pytest tests/ -v --ignore=tests/test_e2e.py
```

## End-to-End Tests

The end-to-end tests create a real uvicorn server on a temporary SQLite database, with Gemini mocked using `GEMINI_MOCK_VERDICT`. The actual HTML pages are driven with Playwright.

Install the browser once:

```bash
uv run --extra dev playwright install chromium
```

Then run:

```bash
uv run --extra dev pytest tests/test_e2e.py -v
```

## Run All Tests

```bash
uv run --extra dev pytest tests/ -v
```

---

# Development Process

## Challenges

1. For human QC, I didn't know if I wanted QC to relabel if the labels don't match, or send the tasks back to labellers. I was leaning more towards sending tasks back to labellers, but then I didn't know what to set the task status to in this case. I contemplated having *qc-checking* and *qc-checked*, but then that would mean the task terminal point would no longer be *labelled*, and there would be no sure way to determine which tasks are truly ready. In the end, I decided to keep *labelled* as the terminal point and to add a new column, *qc_round*, which counts the number of times a task has gone through human QC.
2. If task status was set back to *open*, it would go through the pipeline again but since there was a guardrail on AI reviewing the same jobs, these tasks may never get reviewed. So I decided on per-task AI QC checking by setting three statuses for AI QC, *null*/*pass*/*fail*, and tasks that go through the pipeline again after human QC has AI QC reset to *null*. AI QC would check tasks with AI QC status as *null* in this case.
3. AI QC wasn't running properly because of a model incompatibility issue (model unavailable for free / new users) but I had no way to test manually, so I added a "Run AI QC" button in the human QC frontend to make sure it runs other than relying on the task scheduler.
---

# Project Structure

```text
.
├── index.html
├── .env.example
├── python/
│   ├── main.py
│   ├── seed.py
│   └── ...
├── tests/
│   ├── ...
│   └── test_e2e.py
└── README.md
```
