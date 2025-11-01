FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI application code
COPY search_fastapi.py .

# Expose the port the app runs on
EXPOSE 7860

# Command to run the application
CMD ["uvicorn", "search_fastapi:app", "--host", "0.0.0.0", "--port", "7860"]