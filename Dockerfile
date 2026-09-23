FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MLS_WORKSPACES_DIR=/data/workspaces \
    MLS_DELIVERIES_DIR=/data/deliveries \
    MLS_DRY_RUN=true \
    MLS_PLAYWRIGHT_HEADLESS=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/pyproject.toml ./
RUN python -m pip install --upgrade pip \
    && python -c "import pathlib, subprocess, sys, tomllib; deps = tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *deps])" \
    && python -m playwright install --with-deps chromium

COPY backend/ ./
RUN python -m pip install --no-cache-dir --no-deps .

COPY --from=frontend-builder /app/frontend/dist /app/backend/static

RUN mkdir -p /data/workspaces /data/deliveries

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
