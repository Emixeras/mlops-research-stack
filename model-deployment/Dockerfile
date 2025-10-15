FROM python:3.13-slim

WORKDIR /app

# System deps (if any future wheels need build tools, add here)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first for layer caching
COPY pyproject.toml ./

# Install with pip (simple; could switch to uv/wheels if desired)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy source code (only app.py needed but copy all for flexibility)
COPY app.py ./

EXPOSE 7860
