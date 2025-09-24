#!/usr/bin/env python3
"""
Attach Parquet files to Iceberg table for Kubernetes usage metrics.

This script attaches existing Parquet files from S3/MinIO storage to an Iceberg table,
making them queryable through the Iceberg catalog and Presto.
"""

import os
import sys
import logging
import boto3
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    TimestampType, StringType, IntegerType, LongType, 
    DoubleType, BooleanType, NestedField
)
from pyiceberg.table import Table
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import DayTransform
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:8181")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "minio")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "minio123")
S3_BUCKET = os.getenv("S3_BUCKET", "warehouse")
METRICS_BUCKET = os.getenv("METRICS_BUCKET", "warehouse")
WAREHOUSE_PATH = os.getenv("WAREHOUSE_PATH", "s3://warehouse/")
NAMESPACE = os.getenv("ICEBERG_NAMESPACE", "k8s_metrics")
TABLE_NAME = os.getenv("ICEBERG_TABLE_NAME", "pod_usage_metrics")


class IcebergParquetAttacher:
    """Class to handle attaching Parquet files to Iceberg tables."""
    
    def __init__(self):
        """Initialize the Iceberg catalog and S3 client."""
        self.catalog = self._initialize_catalog()
        self.s3_client = self._initialize_s3_client()
        self.schema = self._define_schema()
        
    def _initialize_catalog(self):
        """Initialize the Iceberg catalog."""
        try:
            catalog_config = {
                "uri": ICEBERG_CATALOG_URI,
                "s3.endpoint": S3_ENDPOINT_URL,
                "s3.access-key-id": S3_ACCESS_KEY_ID,
                "s3.secret-access-key": S3_SECRET_ACCESS_KEY,
                "s3.path-style-access": "true",
                "warehouse": WAREHOUSE_PATH,
                # Additional configuration for MinIO compatibility
                "client.region": "us-east-1",
                "s3.region": "us-east-1"
            }
            
            catalog = load_catalog("rest", **catalog_config)
            logger.info(f"Successfully connected to Iceberg catalog at {ICEBERG_CATALOG_URI}")
            return catalog
            
        except Exception as e:
            logger.error(f"Failed to initialize Iceberg catalog: {e}")
            raise
    
    def _initialize_s3_client(self):
        """Initialize S3 client for accessing Parquet files."""
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                region_name='us-east-1',
                verify=False,
                config=boto3.session.Config(
                    signature_version='s3v4',
                    s3={
                        'addressing_style': 'path'
                    }
                )
            )
            
            logger.info(f"Connecting to S3 at {S3_ENDPOINT_URL}/{METRICS_BUCKET}")
            # Test connection and create bucket if it doesn't exist
            try:
                s3_client.head_bucket(Bucket=METRICS_BUCKET)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info(f"Creating bucket {METRICS_BUCKET}")
                    s3_client.create_bucket(Bucket=METRICS_BUCKET)
                else:
                    raise
            
            logger.info(f"Successfully connected to S3 at {S3_ENDPOINT_URL}")
            return s3_client
            
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
    
    def _define_schema(self) -> Schema:
        """Define the Iceberg table schema based on the Kubernetes metrics structure."""
        return Schema(
            # Make all fields optional to match the actual data structure
            # PyArrow treats any column with potential nulls as optional
            NestedField(1, "timestamp", TimestampType(), required=False),
            NestedField(2, "cluster_id", StringType(), required=False),
            NestedField(3, "node_name", StringType(), required=False),
            NestedField(4, "ec2_instance_id", StringType(), required=False),
            NestedField(5, "pod_id", StringType(), required=False),
            NestedField(6, "namespace", StringType(), required=False),
            NestedField(7, "owner", StringType(), required=False),
            NestedField(8, "node", StringType(), required=False),
            NestedField(9, "cpu_usage_cores", DoubleType(), required=False),
            NestedField(10, "memory_usage_bytes", LongType(), required=False),
            NestedField(11, "requests_cpu_millicores", IntegerType(), required=False),
            NestedField(12, "requests_memory_bytes", LongType(), required=False),
            NestedField(13, "requests_storage_bytes", LongType(), required=False),
            NestedField(14, "limits_cpu_millicores", IntegerType(), required=False),
            NestedField(15, "limits_memory_bytes", LongType(), required=False),
            NestedField(16, "limits_storage_bytes", LongType(), required=False),
            NestedField(17, "labels_json", StringType(), required=False),
            NestedField(18, "annotations_json", StringType(), required=False),
            NestedField(19, "pvc_count", IntegerType(), required=False),
            NestedField(20, "total_pvc_storage_bytes", LongType(), required=False),
            NestedField(21, "pvc_names", StringType(), required=False),
            NestedField(22, "aws_volume_ids", StringType(), required=False),
        )
    
    def create_namespace_if_not_exists(self) -> None:
        """Create namespace if it doesn't exist."""
        try:
            namespaces = list(self.catalog.list_namespaces())
            if (NAMESPACE,) not in namespaces:
                self.catalog.create_namespace(NAMESPACE)
                logger.info(f"Created namespace: {NAMESPACE}")
            else:
                logger.info(f"Namespace {NAMESPACE} already exists")
        except Exception as e:
            logger.error(f"Failed to create namespace {NAMESPACE}: {e}")
            raise
    
    def create_table_if_not_exists(self, force_recreate: bool = False) -> Table:
        """Create Iceberg table if it doesn't exist."""
        table_identifier = f"{NAMESPACE}.{TABLE_NAME}"
        
        if force_recreate:
            try:
                self.catalog.drop_table(table_identifier)
                logger.info(f"Dropped existing table {table_identifier}")
            except Exception:
                pass  # Table might not exist
        
        try:
            # Check if table exists
            table = self.catalog.load_table(table_identifier)
            logger.info(f"Table {table_identifier} already exists")
            return table
            
        except Exception:
            # Table doesn't exist, create it
            logger.info(f"Creating table {table_identifier}")
            
            # Create non-partitioned table for now (to avoid append issues)
            # TODO: Add partitioning back once append to partitioned tables works
            table = self.catalog.create_table(
                identifier=table_identifier,
                schema=self.schema
                # partition_spec=partition_spec  # Commented out for now
            )
            
            logger.info(f"Successfully created table {table_identifier} (non-partitioned)")
            return table
    
    def list_parquet_files(
        self, 
        prefix: str = "",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[str]:
        """List Parquet files in S3 bucket with optional date filtering."""
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            parquet_files = []
            
            for page in paginator.paginate(Bucket=METRICS_BUCKET, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    
                    # Filter by file extension
                    if not key.endswith('.parquet'):
                        continue
                    
                    # Filter by date if specified
                    if start_date or end_date:
                        last_modified = obj['LastModified'].replace(tzinfo=None)
                        
                        if start_date and last_modified < start_date:
                            continue
                        if end_date and last_modified > end_date:
                            continue
                    
                    parquet_files.append(key)
            
            logger.info(f"Found {len(parquet_files)} Parquet files in bucket {METRICS_BUCKET}")
            return sorted(parquet_files)
            
        except Exception as e:
            logger.error(f"Failed to list Parquet files: {e}")
            raise
    
    def validate_parquet_schema(self, s3_key: str) -> bool:
        """Validate that a Parquet file has the expected schema."""
        try:
            # Get Parquet file metadata
            obj = self.s3_client.get_object(Bucket=METRICS_BUCKET, Key=s3_key)
            
            # Read the content into memory to create a seekable buffer
            from io import BytesIO
            buffer = BytesIO(obj['Body'].read())
            
            # Read just the schema without loading data
            parquet_file = pq.ParquetFile(buffer)
            schema = parquet_file.schema
            
            # Basic validation - check for required columns
            required_columns = {'timestamp', 'cluster_id', 'node_name', 'pod_id', 'namespace'}
            actual_columns = set(schema.names)
            
            missing_columns = required_columns - actual_columns
            if missing_columns:
                logger.warning(f"File {s3_key} missing required columns: {missing_columns}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate schema for {s3_key}: {e}")
            return False
    
    def attach_parquet_file(self, table: Table, s3_key: str) -> bool:
        """Attach a single Parquet file to the Iceberg table."""
        try:
            # Validate schema first
            if not self.validate_parquet_schema(s3_key):
                return False
            
            # Construct S3 URI
            s3_uri = f"s3://{METRICS_BUCKET}/{s3_key}"
            
            # Read Parquet file to get data for appending
            obj = self.s3_client.get_object(Bucket=METRICS_BUCKET, Key=s3_key)
            
            # Read the content into memory to create a seekable buffer for pandas
            from io import BytesIO
            buffer = BytesIO(obj['Body'].read())
            df = pd.read_parquet(buffer)
            
            if df.empty:
                logger.warning(f"File {s3_key} is empty, skipping")
                return True
            
            # Convert timestamp column to proper datetime if it's not already
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # Remove timezone to avoid "Unsupported type: timestamp[ns, tz=UTC]" error
                if df['timestamp'].dt.tz is not None:
                    df['timestamp'] = df['timestamp'].dt.tz_localize(None)
                # Convert to microsecond precision (timestamp[us]) as PyIceberg may not support nanoseconds
                df['timestamp'] = df['timestamp'].astype('datetime64[us]')
            
            # Convert DataFrame to PyArrow Table
            arrow_table = pa.Table.from_pandas(df)
            
            logger.info(f"Data schema: {arrow_table.schema}")
            logger.info(f"Table schema: {table.schema()}")
            
            # Fix schema compatibility issues - handle null columns
            columns_to_fix = []
            
            for i, field in enumerate(arrow_table.schema):
                if pa.types.is_null(field.type):
                    logger.info(f"Column {field.name} has null type, will be handled")
                    columns_to_fix.append(field.name)
            
            # Always create df_fixed to avoid variable scope issues
            df_fixed = df.copy()
            
            # Create a new table with fixed columns
            if columns_to_fix:
                logger.info(f"Fixing {len(columns_to_fix)} null columns")
                
                # Set appropriate default values and types for null columns
                for col in columns_to_fix:
                    if col in ['ec2_instance_id', 'owner', 'node', 'labels_json', 'annotations_json', 'pvc_names', 'aws_volume_ids']:
                        df_fixed[col] = df_fixed[col].astype(str).replace('nan', '')  # Convert to string, replace NaN with empty string
                        df_fixed[col] = df_fixed[col].replace('None', '')  # Replace 'None' with empty string
                        df_fixed[col] = df_fixed[col].where(pd.notnull(df_fixed[col]), '')  # Replace NaN with empty string
                    elif col == 'cpu_usage_cores':
                        df_fixed[col] = pd.Series([0.0] * len(df_fixed), dtype='float64')  # Default to 0.0 for double fields
                    elif col == 'memory_usage_bytes':
                        df_fixed[col] = pd.Series([0] * len(df_fixed), dtype='int64')  # Default to 0 for integer fields
                    else:
                        # For any other null columns, convert to string
                        df_fixed[col] = df_fixed[col].astype(str).replace('nan', '')
            else:
                logger.info("No null columns found")
            
            # Fix integer type mismatches (int vs long) and nullability issues
            type_fixes = {
                'requests_cpu_millicores': 'int32',  # Table expects int, data has long
                'limits_cpu_millicores': 'int32',    # Table expects int, data has long
                'pvc_count': 'int32'                 # Table expects int, data has long
            }
            
            for col, dtype in type_fixes.items():
                if col in df_fixed.columns:
                    df_fixed[col] = df_fixed[col].astype(dtype)
                    logger.info(f"Converted {col} to {dtype}")
            
            # Recreate arrow table with all fixes
            arrow_table = pa.Table.from_pandas(df_fixed)
            logger.info(f"Fixed data schema: {arrow_table.schema}")
            
            # Ensure required fields are not null for required columns
            # The table schema shows timestamp, cluster_id, node_name, pod_id, namespace as required
            required_fields = ['timestamp', 'cluster_id', 'node_name', 'pod_id', 'namespace']
            for field in required_fields:
                if field in df_fixed.columns:
                    null_count = df_fixed[field].isnull().sum()
                    if null_count > 0:
                        logger.warning(f"Required field {field} has {null_count} null values, which may cause issues")
            
            # Append data to Iceberg table
            table.append(arrow_table)
            
            logger.info(f"Successfully attached {s3_key} with {len(df)} records")
            return True
            
        except Exception as e:
            logger.error(f"Failed to attach {s3_key}: {e}")
            return False
    
    def attach_multiple_files(
        self, 
        table: Table, 
        s3_keys: List[str],
        batch_size: int = 10
    ) -> Dict[str, int]:
        """Attach multiple Parquet files to the table in batches."""
        results = {"success": 0, "failed": 0, "skipped": 0}
        
        for i in range(0, len(s3_keys), batch_size):
            batch = s3_keys[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} files)")
            
            for s3_key in batch:
                try:
                    if self.attach_parquet_file(table, s3_key):
                        results["success"] += 1
                    else:
                        results["skipped"] += 1
                except Exception as e:
                    logger.error(f"Error processing {s3_key}: {e}")
                    results["failed"] += 1
        
        return results
    
    def get_table_stats(self, table: Table) -> Dict[str, Any]:
        """Get statistics about the Iceberg table."""
        try:
            # Get table metadata
            metadata = table.metadata
            
            stats = {
                "table_uuid": str(metadata.table_uuid),
                "format_version": metadata.format_version,
                "last_updated": metadata.last_updated_ms,
                "schema_id": metadata.current_schema_id,
                "partition_spec_id": metadata.default_spec_id,
                "sort_order_id": metadata.default_sort_order_id,
            }
            
            # Try to get file count and size
            try:
                scan = table.scan()
                files = list(scan.plan_files())
                stats["file_count"] = len(files)
                stats["total_size_bytes"] = sum(f.file_size_in_bytes for f in files)
            except Exception as e:
                logger.warning(f"Could not get file statistics: {e}")
                stats["file_count"] = "unknown"
                stats["total_size_bytes"] = "unknown"
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get table stats: {e}")
            return {}


def main():
    """Main function to orchestrate the Parquet file attachment process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Attach Parquet files to Iceberg table")
    parser.add_argument("--prefix", default="", help="S3 prefix to filter files")
    parser.add_argument("--days-back", type=int, default=7, help="Number of days back to process")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing files")
    parser.add_argument("--dry-run", action="store_true", help="List files but don't attach them")
    parser.add_argument("--force-recreate", action="store_true", help="Drop and recreate table")
    
    args = parser.parse_args()
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days_back)
    
    logger.info(f"Processing files from {start_date} to {end_date}")
    
    try:
        # Initialize attacher
        attacher = IcebergParquetAttacher()
        
        # Create namespace
        attacher.create_namespace_if_not_exists()
        
        # Handle table creation/recreation
        table_identifier = f"{NAMESPACE}.{TABLE_NAME}"
        
        if args.force_recreate:
            try:
                attacher.catalog.drop_table(table_identifier)
                logger.info(f"Dropped existing table {table_identifier}")
            except Exception:
                pass  # Table might not exist
        
        # Create table
        table = attacher.create_table_if_not_exists()
        
        # List Parquet files
        parquet_files = attacher.list_parquet_files(
            prefix=args.prefix,
            start_date=start_date,
            end_date=end_date
        )
        
        if not parquet_files:
            logger.info("No Parquet files found matching criteria")
            return
        
        logger.info(f"Found {len(parquet_files)} files to process")
        
        if args.dry_run:
            logger.info("Dry run mode - listing files only:")
            for file_path in parquet_files:
                logger.info(f"  {file_path}")
            return
        
        # Attach files
        results = attacher.attach_multiple_files(table, parquet_files, args.batch_size)
        
        # Print results
        logger.info(f"Attachment complete:")
        logger.info(f"  Success: {results['success']}")
        logger.info(f"  Failed: {results['failed']}")
        logger.info(f"  Skipped: {results['skipped']}")
        
        # Print table stats
        stats = attacher.get_table_stats(table)
        if stats:
            logger.info(f"Table statistics:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")
        
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
