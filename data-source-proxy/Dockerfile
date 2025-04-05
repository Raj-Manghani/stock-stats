# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed (e.g., for certain libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY ./requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code directly into the WORKDIR
COPY ./app /app

# Make port 8001 available to the world outside this container (FastAPI default is 8000, using 8001 to avoid potential conflicts)
EXPOSE 8001

# Define environment variable (can be overridden by docker-compose)
# These tell uvicorn where to find the FastAPI application instance
# Module is now 'main.py' in WORKDIR
ENV MODULE_NAME="main"
# FastAPI app instance is still named 'app'
ENV VARIABLE_NAME="app"
# Remove PYTHONPATH as it should be unnecessary with WORKDIR /app
# ENV PYTHONPATH=/app

# Run uvicorn server when the container launches
# Use --host 0.0.0.0 to bind to all interfaces inside the container
# Use --port 8001 to match the EXPOSE instruction
# REMOVED --reload temporarily due to potential volume permission issues with watchfiles
# Uvicorn should find 'main:app' relative to the WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
