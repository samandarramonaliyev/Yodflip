# Production image: React build + Django API in ONE web service (same origin, no CORS).
# Used by render.yaml (yodflip-web) and docker-compose.prod.yml.

# ---- 1. Build the React app ---------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty = same origin (the API is served by this same service). Set only if the API lives elsewhere.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ---- 2. Django + gunicorn -------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/frontend_dist \
    RUN_COLLECTSTATIC=0

# Tesseract = OCR fallback when no ANTHROPIC_API_KEY is configured.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend_dist

# Static files are collected at build time (no database needed for this step).
RUN DEBUG=false SECRET_KEY=build-only ALLOWED_HOSTS=build DATABASE_URL=sqlite:////tmp/build.db ALLOW_SQLITE=1 \
    BOT_API_SECRET=build-only-secret-0000 python manage.py collectstatic --noinput -v 0 \
    && chmod +x /app/entrypoint.sh \
    && useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout 120 --access-logfile - --forwarded-allow-ips='*'"]
