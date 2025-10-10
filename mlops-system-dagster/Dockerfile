FROM python:3.11-slim

# Work from the repository root to make DVC paths and cwd intuitive
WORKDIR /workspace

# System deps often needed for building wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and minimal source so pip can resolve the project
# NOTE: build context is ./mlops-system-dagster, so these paths are relative to it
COPY pyproject.toml ./pyproject.toml
COPY src ./src

# Install the project in editable mode with dev extras from pyproject
RUN pip install --no-cache-dir -e .[dev]

# Create dagster home
RUN mkdir -p /dagster_home && chmod -R 777 /dagster_home

# Default command is overridden by compose to run `dagster dev`
EXPOSE 3000
