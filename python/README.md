# Data Labeller — Backend

## Quick Start (no accounts needed)

```bash
cd python
uv sync
uv run uvicorn main:app --reload --reload-dir .
```

This runs the app with a local SQLite database (`data-labeller.db`) — no configuration needed.

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

Creates a sample job with 6 public images and 4 categories. Tasks appear immediately in the labeller page.

## Open the UI

Open `index.html` (in the project root) in a browser to access the landing page, then pick a role:

- **Admin** — create jobs with media URLs and categories
- **Labeller** — annotate media tasks
- **QC Reviewer** — review AI-flagged labels

## Environment Variables

Copy `.env.example` to `.env` and fill in as needed:

| Variable | Required? | Purpose |
|---|---|---|
| `TURSO_DATABASE_URL` | No | Turso DB connection string. Without it, uses local SQLite. |
| `TURSO_AUTH_TOKEN` | No | Turso auth token. Without it, uses local SQLite. |
| `GEMINI_API_KEY` | No | Google Gemini API key. Without it, AI QC is skipped. |
| `GEMINI_MODEL` | No | Gemini model name. Defaults to `gemini-2.5-flash`. |

## Running Tests

```bash
uv run pytest tests/ -v
```
