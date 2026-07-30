FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any are needed (sqlite3 is built-in with python slim)
# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY app/ ./app/
COPY tests/ ./tests/

# Expose port
EXPOSE 8000

# Non-secret defaults (can be overridden at runtime).
# Do not bake auth credentials into the image: pass METER_BUDDY_AUTH_USER /
# METER_BUDDY_AUTH_PASSWORD via `docker run -e`, Compose `environment`/`env_file`,
# or orchestrator secrets (SecretsUsedInArgOrEnv).
ENV METER_BUDDY_DB_PATH="/data/meter_buddy.sqlite3"

# Create data directory
RUN mkdir -p /data

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
