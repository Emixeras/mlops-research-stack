FROM python:3.12.1-slim

WORKDIR /app

# System deps (if any future wheels need build tools, add here)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first for layer caching
COPY pyproject.toml ./

# Install with pip - avoid pip upgrade in same command to prevent segfault
RUN python -m pip install --no-cache-dir .

# Copy source code (only app.py needed but copy all for flexibility)
COPY app.py ./

EXPOSE 7860
