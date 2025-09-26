# Aggregator Service

The aggregator service collects metrics from multiple collector instances, enriches them with Kubernetes metadata, and stores the data in S3-compatible storage in Parquet format.

## Configuration

The aggregator can be configured using the following environment variables:

### Storage Settings

- `S3_BUCKET`: S3 bucket name for storing metrics (default: `k8s-usage-data`)
- `S3_PREFIX`: Prefix path for metrics storage (default: `k8s-metrics/`)
- `AWS_REGION`: AWS region (default: `us-east-1`)
- `AWS_ENDPOINT_URL`: Custom S3 endpoint URL (for MinIO, LocalStack, etc.)
- `AWS_ACCESS_KEY_ID`: AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key

### Cluster Settings

- `CLUSTER_NAME`: Name of the Kubernetes cluster for metadata tagging

### Debug Settings

- `DEBUG_K8S_API`: Enable detailed logging of all Kubernetes API responses (default: `false`)

## Features

### Metrics Collection
- Receives usage metrics from collector DaemonSets
- Validates incoming data against JSON schema
- Provides health check endpoint

### Kubernetes Metadata Enrichment
- Watches nodes, pods, PVCs, and PVs in real-time
- Caches resource metadata for fast lookup
- Enriches metrics with:
  - Pod labels and annotations
  - Resource requests and limits
  - Persistent volume information
  - Node and cluster identifiers

### Data Storage
- Converts enriched metrics to Parquet format
- Uploads to S3-compatible storage
- Organizes data by cluster/date for efficient querying
- Supports partitioned storage for analytics

## Debug Mode

The aggregator includes comprehensive debug logging for troubleshooting Kubernetes API interactions.

### Enable Debug Mode

```yaml
env:
- name: DEBUG_K8S_API
  value: "true"
```

### What Gets Logged

When debug mode is enabled:
- All Kubernetes watch events with full object details
- Cache update operations
- HTTP-level requests/responses to K8s API
- Object serialization and metadata extraction

### Use Cases
- **Troubleshooting**: Pod discovery, node metadata, PVC mapping issues
- **Development**: Understanding K8s object structures and relationships
- **Performance**: Monitoring API response times and cache efficiency

⚠️ **Warning**: Debug mode significantly increases log volume and memory usage. Use sparingly in production.

For detailed debug mode documentation, see [DEBUG_MODE_GUIDE.md](../DEBUG_MODE_GUIDE.md).

## API Endpoints

### POST /metrics
Receives metrics payloads from collector instances.

**Request Body:**
```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "node_name": "worker-node-1",
  "hostname": "worker-node-1",
  "ec2_instance_id": "i-1234567890abcdef0",
  "pods": [
    {
      "pod_id": "pod-uid-123",
      "namespace": "default",
      "name": "my-app",
      "cpu_usage_cores": 0.5,
      "memory_usage_bytes": 1073741824,
      "net_tx_bytes": 1024,
      "net_rx_bytes": 2048,
      "pod_start_time": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok"
}
```

### GET /health
Health check endpoint with watcher status.

**Response:**
```json
{
  "status": "healthy",
  "debug_k8s_api": false,
  "watchers_initialized": {
    "nodes": true,
    "pods": true,
    "pvcs": true,
    "pvs": true
  },
  "all_watchers_ready": true
}
```

## Deployment

The aggregator runs as a Deployment and requires:

- **ClusterRole permissions** for watching nodes, pods, PVCs, and PVs
- **S3 credentials** for data storage
- **Network connectivity** to Kubernetes API server and S3 endpoint

See the deployment YAML files in the `k8s/` directory for complete examples.

## Data Format

Stored metrics are converted to Parquet format with the following schema:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | string | Collection timestamp (ISO 8601) |
| cluster_id | string | Cluster identifier |
| node_name | string | Kubernetes node name |
| ec2_instance_id | string | AWS EC2 instance ID (if available) |
| pod_id | string | Pod UID |
| namespace | string | Pod namespace |
| owner | string | Pod owner reference |
| cpu_usage_cores | double | CPU usage in cores |
| memory_usage_bytes | long | Memory usage in bytes |
| net_tx_bytes | long | Network transmit bytes |
| net_rx_bytes | long | Network receive bytes |
| requests_cpu_millicores | long | CPU requests in millicores |
| requests_memory_bytes | long | Memory requests in bytes |
| limits_cpu_millicores | long | CPU limits in millicores |
| limits_memory_bytes | long | Memory limits in bytes |
| labels | array[string] | Pod labels as key=value pairs |
| annotations | array[string] | Pod annotations as key=value pairs |
| pvc_count | int | Number of PVCs mounted |
| total_pvc_storage_bytes | long | Total PVC storage requested |
| pvc_names | array[string] | Names of mounted PVCs |
| aws_volume_ids | array[string] | AWS EBS volume IDs |

## Monitoring and Troubleshooting

### Check Aggregator Status
```bash
kubectl get pods -n kube-system -l app=aggregator
kubectl logs deployment/aggregator -n kube-system
```

### Verify S3 Connectivity
```bash
kubectl logs deployment/aggregator -n kube-system | grep -E "(S3|upload)"
```

### Monitor Watch Status
```bash
curl http://aggregator.kube-system.svc.cluster.local:8888/health
```

### Debug Mode Troubleshooting
```bash
# Enable debug logging
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true

# Check debug logs
kubectl logs deployment/aggregator -n kube-system | grep "K8S API"

# Disable debug logging
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=false
```

## Security Considerations

- Uses non-root container user for security
- Requires only read permissions for Kubernetes resources
- S3 credentials should be stored in Kubernetes secrets
- Debug mode may expose sensitive cluster information in logs
- Implements JSON schema validation for incoming data