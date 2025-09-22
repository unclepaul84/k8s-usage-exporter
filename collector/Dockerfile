# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the collector script
COPY collector.py .

# Set environment variables with defaults
ENV PUSH_ENDPOINT=http://aggregator:8080/metrics
ENV KUBELET_ENDPOINT=http://127.0.0.1:10255/stats/summary
ENV SCRAPE_INTERVAL=30

# Run the collector
CMD ["python", "-u", "collector.py"]