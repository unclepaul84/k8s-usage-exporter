# Multi-architecture Python image (supports linux/amd64, linux/arm64)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy and install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the collector script
COPY collector.py .
COPY README.md .

# Set environment variables with defaults
ENV PUSH_ENDPOINT=http://aggregator:8080/metrics
ENV KUBELET_ENDPOINT=https://127.0.0.1:10250/stats/summary
ENV SCRAPE_INTERVAL=30
ENV ENABLE_EC2_INSTANCE_ID=true
ENV EC2_METADATA_TOKEN_TTL=21600
ENV FORCE_IMDSV1=false

# Create non-root user for security
RUN groupadd -r collector && useradd -r -g collector collector
USER collector

# Run the collector
CMD ["python", "-u", "collector.py"]