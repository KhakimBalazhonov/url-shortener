FROM python:3.14-slim AS builder

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Оптимизации uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Зависимости пересобираются только при изменении pyproject.toml или uv.lock
COPY pyproject.toml uv.lock ./

# Установка библиотек
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY entrypoint.sh ./

RUN uv sync --frozen --no-dev

FROM python:3.14-slim

WORKDIR /app

# Непривилегированный пользователь
RUN useradd -m -u 1000 appuser \
    && chown appuser:appuser /app

COPY --from=builder --chown=appuser:appuser /app /app

# Делает entrypoint.sh скрипт исполняемым
RUN chmod +x /app/entrypoint.sh

# PATH — где искать команды (python, uvicorn, celery), PYTHONPATH — где искать код,
# PYTHONUNBUFFERED — логи без задержки, PYTHONDONTWRITEBYTECODE — не создавать __pycache__
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
