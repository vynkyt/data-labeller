FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app/python

COPY python/pyproject.toml python/uv.lock ./
RUN uv sync --frozen --no-dev

COPY python/ .
COPY *.html ../

ENV PORT=10000
ENV PYTHONUNBUFFERED=1

EXPOSE 10000

CMD ["sh", "-c", "uv run --no-sync uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
