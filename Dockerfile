# ------------------------------------------------------------
# Dockerfile for LinkedIn Profile Extractor (FastAPI + Crawl4AI + Gemini)
# ------------------------------------------------------------

FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Install system dependencies for Playwright and Chromium
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium)
RUN python -m playwright install --with-deps chromium

# Copy all project files
COPY . .

# Expose FastAPI default port (Hugging Face Spaces uses 7860)
EXPOSE 7860

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
