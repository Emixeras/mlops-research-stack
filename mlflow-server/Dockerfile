FROM python:3.11-slim

WORKDIR /mlflow

# Install system dependencies for PostgreSQL driver build and clean up
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install MLflow with PostgreSQL support
RUN pip install --no-cache-dir mlflow psycopg2-binary

# Prepare artifacts directory (will be backed by a named volume)
RUN mkdir -p /mlflow-artifacts

EXPOSE 5000