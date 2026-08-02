FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    METER_BUDDY_DB_PATH="/data/meter_buddy.sqlite3"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# Do not bake auth credentials into the image: pass METER_BUDDY_AUTH_USER /
# METER_BUDDY_AUTH_PASSWORD via `docker run -e`, Compose, or orchestrator secrets.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
