# Collector Service

The collector service runs as a DaemonSet on each Kubernetes node and collects resource usage metrics from the kubelet, optionally including EC2 instance metadata.

## Configuration

The collector can be configured using the following environment variables:

### Core Settings

- `PUSH_ENDPOINT`: URL of the aggregator service (default: `http://aggregator:8080/metrics`)
- `SCRAPE_INTERVAL`: Interval in seconds between metric collections (default: `30`)
- `JITTER_PERCENT`: Percentage of jitter to add to scrape interval to prevent thundering herd (default: `20`)
- `MAX_CONSECUTIVE_FAILURES`: Number of consecutive failures before the collector exits (default: `5`)
- `KUBELET_ENDPOINT`: Kubelet stats endpoint (default: `https://127.0.0.1:10250/stats/summary`)

### EC2 Instance Metadata Settings

- `ENABLE_EC2_INSTANCE_ID`: Enable/disable EC2 instance ID collection (default: `true`)
- `EC2_METADATA_TOKEN_TTL`: TTL in seconds for IMDSv2 session tokens (default: `21600` - 6 hours)
- `FORCE_IMDSV1`: Force the use of IMDSv1 only, skipping IMDSv2 (default: `false`)

### Debug Settings

- `DEBUG_K8S_API`: Enable detailed logging of all HTTP requests and responses (default: `false`)

## AWS Instance Metadata Service (IMDS) Support

The collector supports both IMDSv1 and IMDSv2 for retrieving EC2 instance metadata:

### IMDSv2 (Default)

The collector will first attempt to use IMDSv2, which provides enhanced security through token-based authentication:

1. **Token Request**: Makes a PUT request to `http://169.254.169.254/latest/api/token` with a TTL header
2. **Metadata Request**: Uses the received token in subsequent metadata requests via the `X-aws-ec2-metadata-token` header

### IMDSv1 (Fallback)

If IMDSv2 fails, the collector automatically falls back to IMDSv1 for backward compatibility. This uses simple HTTP GET requests without authentication.

### Configuration Examples

#### Standard IMDSv2 with fallback (recommended)
```yaml
env:
- name: ENABLE_EC2_INSTANCE_ID
  value: "true"
- name: EC2_METADATA_TOKEN_TTL
  value: "21600"  # 6 hours
```

#### Force IMDSv1 only (not recommended, for compatibility only)
```yaml
env:
- name: ENABLE_EC2_INSTANCE_ID
  value: "true"
- name: FORCE_IMDSV1
  value: "true"
```

#### Disable EC2 metadata collection
```yaml
env:
- name: ENABLE_EC2_INSTANCE_ID
  value: "false"
```

#### Enable debug logging
```yaml
env:
- name: DEBUG_K8S_API
  value: "true"
```

## Debug Mode

The collector includes comprehensive debug logging for troubleshooting HTTP interactions with the kubelet and aggregator services.

### Enable Debug Mode

```yaml
env:
- name: DEBUG_K8S_API
  value: "true"
```

### What Gets Logged

When debug mode is enabled:

#### 1. HTTP Request/Response Details
All HTTP requests and responses with full details:
```
DEBUG - HTTP [GET] https://127.0.0.1:10250/stats/summary -> 200 OK
DEBUG - Response headers: {'content-type': 'application/json', 'content-length': '12345'}
DEBUG - Response JSON structure: {
  "node": "<dict(5)>",
  "pods": "<list(15)>"
}
```

#### 2. Kubelet Response Analysis
Structured analysis of kubelet responses:
```
DEBUG - Kubelet response summary: {
  "node_name": "worker-node-1", 
  "pod_count": 15,
  "node_cpu_usage": 2500000000,
  "node_memory_usage": 4294967296
}
DEBUG - Pod 1 details: {
  "pod_name": "kube-system/coredns-12345",
  "cpu_usage": 50000000,
  "memory_usage": 67108864
}
```

#### 3. EC2 Metadata Requests
IMDSv2 and IMDSv1 interactions:
```
DEBUG - HTTP [PUT] http://169.254.169.254/latest/api/token -> 200 OK
DEBUG - HTTP [GET] http://169.254.169.254/latest/meta-data/instance-id -> 200 OK
DEBUG - Response content: i-1234567890abcdef0
```

#### 4. Aggregator Communication
Payload submission to aggregator:
```
DEBUG - HTTP [POST] http://aggregator:8888/metrics -> 200 OK
DEBUG - Request data: {
  "timestamp": "2024-01-01T00:00:00Z",
  "node_name": "worker-node-1",
  "pods": [...]
}
```

### Use Cases

#### Troubleshooting
- **Kubelet Access Issues**: Verify SSL, authentication, and endpoint connectivity
- **EC2 Metadata Problems**: Debug IMDSv2/v1 token acquisition and metadata retrieval  
- **Aggregator Communication**: Monitor payload submission and response handling
- **Network Connectivity**: Trace HTTP-level communication issues

#### Performance Analysis
- **Response Times**: Monitor kubelet and aggregator response latencies
- **Payload Size**: Track metrics payload size and compression
- **Error Patterns**: Identify recurring HTTP error patterns

#### Development
- **API Understanding**: See complete kubelet response structures
- **Payload Validation**: Verify correct data extraction and formatting
- **Integration Testing**: Validate end-to-end communication flow

### Performance Impact

⚠️ **Important**: Debug mode significantly increases log volume.

#### Log Volume
- **Normal**: ~5-10 log lines per collection cycle
- **Debug**: ~50-200+ log lines per collection cycle

#### Memory Usage
- **Normal**: ~20MB baseline memory
- **Debug**: +10-50MB depending on cluster size and payload complexity

#### Network Impact
- No additional network requests (same HTTP calls, just logged)
- May slow processing due to extensive logging overhead

### Configuration Examples

#### Enable for Troubleshooting
```yaml
env:
- name: DEBUG_K8S_API
  value: "true"
```

#### Runtime Configuration
```bash
# Enable debug on running DaemonSet
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true

# Disable debug after troubleshooting  
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=false
```

#### Production Safety
Always start with debug disabled:
```yaml
env:
- name: DEBUG_K8S_API
  value: "false"  # Safe default
```

## Deployment

The collector runs as a DaemonSet and requires:

- `hostNetwork: true` for access to the kubelet on localhost
- Appropriate RBAC permissions for accessing node stats
- Service account token mounted for kubelet authentication

See the deployment YAML files in the `k8s/` directory for complete examples.

## Security Considerations

- **IMDSv2 is recommended** over IMDSv1 for enhanced security
- The collector uses short timeouts (2 seconds) for metadata requests to avoid hanging
- Session tokens are cached per collection cycle to minimize API calls
- All HTTP requests to IMDS use a 2-second timeout to prevent blocking

## Monitoring and Troubleshooting

## Monitoring and Troubleshooting

### Check Collector Status
```bash
kubectl get pods -n kube-system -l app=cost-collector
kubectl get daemonset -n kube-system cost-collector
```

### View Collector Logs
```bash
# View logs from all collector pods
kubectl logs daemonset/cost-collector -n kube-system

# View logs from specific node
kubectl logs -n kube-system -l app=cost-collector --field-selector spec.nodeName=worker-node-1

# Follow logs in real-time
kubectl logs -f daemonset/cost-collector -n kube-system
```

### Debug Mode Troubleshooting

#### Enable Debug Logging
```bash
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true
```

#### Common Debug Scenarios

**Kubelet Access Issues:**
```bash
# Check for authentication errors
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(401|403|kubelet)"

# Verify SSL/TLS issues
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(SSL|TLS|certificate)"
```

**EC2 Metadata Problems:**
```bash
# Monitor IMDSv2/v1 requests
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(169.254.169.254|IMDSv|token)"

# Check instance ID retrieval
kubectl logs daemonset/cost-collector -n kube-system | grep "Retrieved EC2 instance ID"
```

**Aggregator Communication:**
```bash
# Monitor payload submission
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(POST|aggregator|Pushed)"

# Check for network timeouts
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(timeout|connection)"
```

#### Disable Debug Logging
```bash
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=false
```

### Performance Monitoring
```bash
# Check resource usage
kubectl top pods -n kube-system -l app=cost-collector

# Monitor collection frequency
kubectl logs daemonset/cost-collector -n kube-system | grep "Sleeping for"

# Count successful collections
kubectl logs daemonset/cost-collector -n kube-system | grep "Pushed.*pod metrics" | wc -l
```

## Security Considerations

- Uses non-root container user for security
- Requires service account token for kubelet authentication
- IMDSv2 provides enhanced security over IMDSv1 for EC2 metadata access
- Debug mode may expose sensitive cluster information in logs
- EC2 instance IDs and node metadata are collected for cost attribution

For detailed debug mode documentation covering both collector and aggregator, see [DEBUG_MODE_GUIDE.md](../DEBUG_MODE_GUIDE.md).