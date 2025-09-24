# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the aggregator script and configuration
COPY aggregator.py .
COPY gunicorn.conf.py .

# Expose port 8080 for the Flask app
EXPOSE 8888

# Run the aggregator Flask service with Gunicorn
CMD ["gunicorn", "--config", "gunicorn.conf.py", "aggregator:app"]