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

## Live Demo

A hosted demo is available here: [nest link](https://datalabeller.vkyt.hackclub.app/)

* The demo database is pre-seeded with a sample job (6 images, 4 categories), so the labeller page has tasks ready immediately.
* AI QC runs on the hosted demo only if a `GEMINI_API_KEY` was configured by the owner (see Turso / Gemini below). Everything else works regardless.


### Alternative: Render

A hosted demo is also available in [render](https://data-labeller-6rw0.onrender.com/).

* No setup needed. Open the link and pick a role.
* The free tier sleeps after ~15 minutes of inactivity; if it doesn't load, wait ~1 minute and refresh while it wakes up.
* Demo data resets occasionally. To get the seeded sample job back, visit `<your-render-url-here>/admin.html`, or run the local setup below and use `seed.py`.
* AI QC runs on the hosted demo only if a `GEMINI_API_KEY` was configured by the owner (see Turso / Gemini below). Everything else works regardless.

## Prerequisites

You need two things installed (no accounts, API keys, or databases required):

1. **Git**: [git-scm.com/downloads](https://git-scm.com/downloads)
2. **uv** (Python package manager); install with one of:

   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Verify it works: `uv --version` should print a version number.

## Quick Start

**Step 1: Clone the repository**

```bash
git clone https://github.com/vynkyt/data-labeller.git
cd data-labeller
```

**Step 2: Start the server**

```bash
cd python
uv sync
uv run uvicorn main:app --reload
```

The first run takes a minute or two while uv downloads Python and dependencies. When you see `Application startup complete.` the server is running. **Leave this terminal open** as closing it stops the app.

**Step 3: Open the app**

Open **http://localhost:8000** in your browser. You should see the Data Labeller landing page with three role cards (Admin, Labeller, QC Reviewer).

## Load Demo Data

With the server still running from Step 2, open a **second terminal**, then:

```bash
cd data-labeller/python
uv run python seed.py
```

You should see `Created demo job with 6 tasks`. This creates a sample job with 6 public images and 4 categories (animal, vehicle, food, nature).

## Suggested Demo Walkthrough

1. **Labeller**: go to http://localhost:8000/labeller.html, enter any name, and label a few of the seeded images.
2. **AI QC**: automatic; Gemini samples and verifies labels if configured (skipped without an API key).
3. **QC Reviewer**: go to http://localhost:8000/qc.html to review flagged labels: approve correct ones or send them back for relabelling.
4. Optionally visit http://localhost:8000/admin.html to create your own job with any image URLs and categories.

To stop the app, press `Ctrl+C` in the first terminal.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `uv: command not found` | Install uv (see Prerequisites), then close and reopen your terminal. |
| Port 8000 already in use | Stop whatever is using it, or start on another port: `uv run uvicorn main:app --reload --port 8001` (then use `http://localhost:8001` everywhere instead). |
| `seed.py` prints "Could not connect" | The server isn't running. Complete Step 2 first and keep that terminal open. |
| Seeded images don't load | The demo uses public placeholder images from picsum.photos — check your internet connection. |
| Database issues / want a fresh start | Stop the server, delete `python/data-labeller.db`, and restart. |

---

# Turso / Gemini

Everything works out of the box with local SQLite and no API keys — this section is entirely optional.

If you want to use Turso for the database and/or Gemini for AI quality control:

1. Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
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
├── admin.html
├── labeller.html
├── qc.html
├── Dockerfile
├── render.yaml
├── python/
│   ├── main.py
│   ├── seed.py
│   └── .env.example
└── README.md
```
