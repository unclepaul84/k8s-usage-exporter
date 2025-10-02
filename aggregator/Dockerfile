# Multi-architecture Python image (supports linux/amd64, linux/arm64)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy and install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the aggregator files
COPY aggregator.py .
COPY payload_schema.json .
COPY server_config.py .

# Create non-root user for security
RUN groupadd -r aggregator && useradd -r -g aggregator aggregator

# Change ownership of app directory
RUN chown -R aggregator:aggregator /app
USER aggregator

# Expose port 8888 for the Flask app
EXPOSE 8888

# Run the aggregator Flask service with Waitress
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8888", "--threads=4", "--connection-limit=1000", "--cleanup-interval=30", "--channel-timeout=120", "aggregator:app"]