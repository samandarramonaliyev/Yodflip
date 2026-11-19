# Optional: the same single service as on Render, as a container (for local production-like runs
# with `docker compose up --build`). Render itself uses the native Python runtime + build.sh.

FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/frontend_dist RUN_COLLECTSTATIC=0
# Tesseract = OCR fallback without ANTHROPIC_API_KEY (not available on Render's native runtime).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend_dist
RUN DEBUG=false SECRET_KEY=build-only ALLOWED_HOSTS=build DATABASE_URL=sqlite:////tmp/build.db ALLOW_SQLITE=1 \
    python manage.py collectstatic --noinput -v 0 \
    && chmod +x /app/entrypoint.sh && useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
