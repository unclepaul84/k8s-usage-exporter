# Iceberg Parquet File Attacher

This directory contains tools for attaching Parquet files from the Kubernetes usage exporter to Apache Iceberg tables, making them queryable through SQL engines like Presto.

## Overview

The Kubernetes usage exporter collects metrics and stores them as Parquet files in S3-compatible storage (MinIO). This tool bridges the gap by:

1. **Discovering** existing Parquet files in S3/MinIO storage
2. **Validating** their schema compatibility with the Iceberg table
3. **Attaching** them to an Iceberg table for SQL querying
4. **Managing** the table lifecycle and partitioning

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kubernetes    │    │     MinIO       │    │    Iceberg      │
│   Metrics       │───▶│   (S3 Storage)  │───▶│     Table       │
│   (Parquet)     │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                              ┌─────────────────┐
                                              │     Presto      │
                                              │   (SQL Query)   │
                                              └─────────────────┘
```

## Files

- `attach_parquet.py` - Main attachment script with full functionality
- `create_sample_table.py` - Create sample Iceberg tables for testing and demonstration
- `example_usage.py` - Example usage patterns and demonstrations
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container image for the attacher
- `docker-compose.yaml` - Complete stack including Iceberg infrastructure

## Quick Start

### 1. Start the Infrastructure

```bash
# Start all services (MinIO, PostgreSQL, Iceberg REST, Presto)
docker compose up -d
```

### 2. Install Dependencies (if running locally)

```bash
pip install -r requirements.txt
```

### 3. Create Sample Tables (Optional)

Before attaching real data, you can create sample tables for testing:

```bash
# Create both sample tables with some test data
python create_sample_table.py

# Create just the main pod usage metrics table
python create_sample_table.py --create-pod-table

# Create a simple table and populate with 100 sample records
python create_sample_table.py --create-simple-table --populate-simple-data 100

# Create pod table and populate with 1000 sample records from last 7 days
python create_sample_table.py --create-pod-table --populate-pod-data 1000 --days-back 7

# List all tables
python create_sample_table.py --list-tables

# Show information about a specific table
python create_sample_table.py --show-info simple_metrics
```

### 4. Attach Parquet Files

```bash
# Attach files from the last 7 days
python attach_parquet.py

# Attach files with specific prefix
python attach_parquet.py --prefix "k8s-metrics/production-cluster/"

# Dry run to see what files would be processed
python attach_parquet.py --dry-run

# Process files from last 30 days in batches of 5
python attach_parquet.py --days-back 30 --batch-size 5
```

### 5. Query the Data

Access Presto at http://localhost:8080 and run SQL queries:

```sql
-- Show available tables
SHOW TABLES FROM iceberg.k8s_metrics;

-- Query recent pod metrics
SELECT 
    cluster_id,
    namespace,
    COUNT(*) as pod_count,
    AVG(cpu_usage_cores) as avg_cpu,
    AVG(memory_usage_bytes) as avg_memory
FROM iceberg.k8s_metrics.pod_usage_metrics 
WHERE timestamp > current_timestamp - interval '1' day
GROUP BY cluster_id, namespace
ORDER BY avg_cpu DESC;
```

## Creating Iceberg Tables

There are several ways to create Iceberg tables in this project:

### Method 1: Using the Sample Table Creator (Recommended for Testing)

The `create_sample_table.py` script provides the easiest way to create tables with sample data:

```bash
# Create all sample tables and populate with test data
python create_sample_table.py

# Create specific table types
python create_sample_table.py --create-pod-table
python create_sample_table.py --create-simple-table

# Add sample data to existing tables
python create_sample_table.py --populate-pod-data 1000
python create_sample_table.py --populate-simple-data 100
```

### Method 2: Using the Parquet Attacher

The `attach_parquet.py` script automatically creates tables when attaching Parquet files:

```bash
# This will create the pod_usage_metrics table if it doesn't exist
python attach_parquet.py

# Force recreate the table
python attach_parquet.py --force-recreate
```

### Method 3: Direct SQL through Presto

You can also create tables directly through Presto SQL:

```sql
-- Connect to Presto at http://localhost:8080
-- Create a simple table
CREATE TABLE iceberg.k8s_metrics.my_test_table (
    id BIGINT,
    name VARCHAR,
    created_at TIMESTAMP,
    cpu_usage DOUBLE
) WITH (
    partitioning = ARRAY['day(created_at)']
);

-- Insert sample data
INSERT INTO iceberg.k8s_metrics.my_test_table VALUES 
(1, 'pod-1', TIMESTAMP '2025-09-23 10:00:00', 0.5),
(2, 'pod-2', TIMESTAMP '2025-09-23 11:00:00', 0.8),
(3, 'pod-3', TIMESTAMP '2025-09-23 12:00:00', 0.3);
```

### Method 4: Programmatic Creation

You can use the Python API directly:

```python
from create_sample_table import SampleTableCreator

# Initialize
creator = SampleTableCreator()
creator.create_namespace_if_not_exists()

# Create tables
creator.create_pod_metrics_table("my_custom_table")
creator.create_simple_metrics_table("simple_test")

# Generate and add sample data
data = creator.generate_simple_sample_data(num_records=50)
creator.populate_table_with_data("simple_test", data)

# List and inspect
creator.list_tables()
creator.show_table_info("simple_test")
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ICEBERG_CATALOG_URI` | `http://localhost:8181` | Iceberg REST catalog endpoint |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | S3/MinIO endpoint |
| `S3_ACCESS_KEY_ID` | `minio` | S3 access key |
| `S3_SECRET_ACCESS_KEY` | `minio123` | S3 secret key |
| `S3_BUCKET` | `warehouse` | Iceberg warehouse bucket |
| `METRICS_BUCKET` | `k8s-usage-data` | Bucket containing Parquet files |
| `WAREHOUSE_PATH` | `s3://warehouse/` | Iceberg warehouse path |
| `ICEBERG_NAMESPACE` | `k8s_metrics` | Iceberg namespace/database |
| `ICEBERG_TABLE_NAME` | `pod_usage_metrics` | Table name |

### Command Line Options

```bash
python attach_parquet.py --help
```

- `--prefix` - S3 prefix to filter files (e.g., "k8s-metrics/cluster1/")
- `--days-back` - Number of days back to process (default: 7)
- `--batch-size` - Batch size for processing files (default: 10)
- `--dry-run` - List files but don't attach them
- `--force-recreate` - Drop and recreate the table

## Schema

The Iceberg table schema matches the Kubernetes metrics structure:

```sql
CREATE TABLE pod_usage_metrics (
    timestamp TIMESTAMP,
    cluster_id VARCHAR,
    node_name VARCHAR,
    ec2_instance_id VARCHAR,
    pod_id VARCHAR,
    namespace VARCHAR,
    owner VARCHAR,
    node VARCHAR,
    cpu_usage_cores DOUBLE,
    memory_usage_bytes BIGINT,
    requests_cpu_millicores INTEGER,
    requests_memory_bytes BIGINT,
    requests_storage_bytes BIGINT,
    limits_cpu_millicores INTEGER,
    limits_memory_bytes BIGINT,
    limits_storage_bytes BIGINT,
    labels_json VARCHAR,
    annotations_json VARCHAR,
    pvc_count INTEGER,
    total_pvc_storage_bytes BIGINT,
    pvc_names VARCHAR,
    aws_volume_ids VARCHAR
) PARTITIONED BY (day(timestamp));
```

## Usage Patterns

### 1. Initial Table Setup

```python
from attach_parquet import IcebergParquetAttacher

attacher = IcebergParquetAttacher()
attacher.create_namespace_if_not_exists()
table = attacher.create_table_if_not_exists()
```

### 2. Batch Processing

```python
# Get files from specific time range
files = attacher.list_parquet_files(
    prefix="k8s-metrics/production/",
    start_date=datetime.now() - timedelta(days=7)
)

# Process in batches
results = attacher.attach_multiple_files(table, files, batch_size=20)
print(f"Success: {results['success']}, Failed: {results['failed']}")
```

### 3. Schema Validation

```python
# Validate individual files before processing
for file_path in parquet_files:
    if attacher.validate_parquet_schema(file_path):
        attacher.attach_parquet_file(table, file_path)
```

### 4. Table Statistics

```python
stats = attacher.get_table_stats(table)
print(f"Files: {stats['file_count']}, Size: {stats['total_size_bytes']} bytes")
```

## Running in Docker

### Build and Run

```bash
# Build the image
docker build -t iceberg-attacher .

# Run with custom parameters
docker run --rm -it \
    --network iceberg_default \
    -e ICEBERG_CATALOG_URI=http://iceberg-rest:8181 \
    -e S3_ENDPOINT_URL=http://minio:9000 \
    iceberg-attacher python attach_parquet.py --days-back 30
```

### Using Docker Compose

```bash
# Start all services including attacher
docker compose up -d

# Execute attachment in the running container
docker compose exec iceberg-attacher python attach_parquet.py --days-back 7

# Run examples
docker compose exec iceberg-attacher python example_usage.py
```

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Ensure all services are running: `docker compose ps`
   - Check network connectivity between containers
   - Verify S3 credentials and endpoints

2. **Schema Mismatches**
   - Run with `--dry-run` to validate files first
   - Check Parquet file structure: `parquet-tools schema file.parquet`
   - Ensure timestamp columns are properly formatted

3. **Permission Issues**
   - Verify S3/MinIO access keys have read permissions
   - Check Iceberg catalog permissions for table creation

4. **Performance Issues**
   - Reduce `--batch-size` for large files
   - Use `--prefix` to limit file scope
   - Process files in smaller date ranges

### Monitoring

```bash
# Check table status
docker compose exec iceberg-attacher python -c "
from attach_parquet import IcebergParquetAttacher
attacher = IcebergParquetAttacher()
table = attacher.catalog.load_table('k8s_metrics.pod_usage_metrics')
stats = attacher.get_table_stats(table)
print(stats)
"

# List recent files
docker compose exec iceberg-attacher python attach_parquet.py --dry-run --days-back 1
```

## Advanced Usage

### Custom Partitioning

Modify the `_define_schema()` method in `attach_parquet.py` to change partitioning strategy:

```python
# Partition by cluster and day
partition_spec = PartitionSpec(
    PartitionField(source_id=2, field_id=1000, transform=IdentityTransform(), name="cluster_id"),
    PartitionField(source_id=1, field_id=1001, transform=DayTransform(), name="day")
)
```

### Custom Schema Evolution

The script supports automatic schema evolution. New columns in Parquet files will be added to the Iceberg table automatically.

### Integration with Airflow/Cron

```bash
# Example cron job for daily processing
0 2 * * * /usr/bin/docker compose -f /path/to/docker-compose.yaml exec -T iceberg-attacher python attach_parquet.py --days-back 1
```

## Contributing

1. Follow the existing code structure and patterns
2. Add comprehensive error handling and logging
3. Include unit tests for new functionality
4. Update documentation for new features

## Performance Considerations

- **Batch Size**: Larger batches are more efficient but use more memory
- **Partitioning**: Day-based partitioning optimizes query performance
- **File Size**: Optimal Parquet file size is 128MB-1GB
- **Compression**: Use Snappy compression for best performance balance

## Security Notes

- Use IAM roles instead of hardcoded credentials in production
- Enable SSL/TLS for all network communications
- Implement proper network segmentation
- Regularly rotate access keys and passwords