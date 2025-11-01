# ------------------------------------------------------------
# Dockerfile for LinkedIn Profile Extractor (FastAPI + Crawl4AI)
# ------------------------------------------------------------

# Use a lightweight Python base image
FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose FastAPI default port
EXPOSE 7860

# Run FastAPI app using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
