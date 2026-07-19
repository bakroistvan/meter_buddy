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

# Set default env variables (can be overridden at runtime)
ENV METER_BUDDY_AUTH_USER="meter-buddy"
ENV METER_BUDDY_AUTH_PASSWORD="change-me"
ENV METER_BUDDY_DB_PATH="/data/meter_buddy.sqlite3"

# Create data directory
RUN mkdir -p /data

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
