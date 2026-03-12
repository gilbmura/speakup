# ── SpeakUp Dockerfile ────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps for Pillow + PyMySQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /speakup

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create uploads directory
RUN mkdir -p app/static/uploads

# Expose port
EXPOSE 8000

# Startup: run migrations, seed, then start app
CMD ["sh", "-c", "python seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
