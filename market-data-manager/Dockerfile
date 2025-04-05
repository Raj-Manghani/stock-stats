# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install build dependencies needed for psycopg2-binary and potentially others
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY ./requirements.txt /app/requirements.txt

# Install Python dependencies
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code directly into the WORKDIR
COPY ./app /app

# Make port 8002 available (using a different port than the proxy)
EXPOSE 8002

# Define environment variable for the FastAPI app instance
ENV MODULE_NAME="main"
ENV VARIABLE_NAME="app"

# Run uvicorn server when the container launches
# Use --host 0.0.0.0 to bind to all interfaces inside the container
# Use --port 8002 to match the EXPOSE instruction
# No --reload for this service initially, as permissions might still be an issue
# Clean pyc files before starting to ensure fresh code is used
CMD find /app -name "*.pyc" -delete && uvicorn main:app --host 0.0.0.0 --port 8002
