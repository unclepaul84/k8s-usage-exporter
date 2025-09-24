FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY attach_parquet.py .


# Set environment variables with defaults
ENV ICEBERG_CATALOG_URI=http://iceberg-rest:8181
ENV S3_ENDPOINT_URL=http://minio:9000
ENV S3_ACCESS_KEY_ID=minio
ENV S3_SECRET_ACCESS_KEY=minio123
ENV S3_BUCKET=warehouse
ENV METRICS_BUCKET=warehouse
ENV WAREHOUSE_PATH=s3://warehouse/
ENV ICEBERG_NAMESPACE=k8s_metrics
ENV ICEBERG_TABLE_NAME=pod_usage_metrics

# Make scripts executable
RUN chmod +x attach_parquet.py

# Default command
CMD ["python", "-u" ,"attach_parquet.py", "--help"]