uv run --env-file .env uvicorn main:app --reload --reload-dir .

uv run --extra dev pytest tests/test_e2e.py -v