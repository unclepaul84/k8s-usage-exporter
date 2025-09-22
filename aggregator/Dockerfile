# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the aggregator script
COPY aggregator.py .

# Expose port 8080 for the Flask app
EXPOSE 8080

# Run the aggregator Flask service
CMD ["python", "-u", "aggregator.py"]