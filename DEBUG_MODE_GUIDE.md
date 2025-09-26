# Debug Mode for Kubernetes API Calls

Both the aggregator and collector services include comprehensive debug logging for all HTTP interactions with Kubernetes APIs and other services. This feature is controlled by the `DEBUG_K8S_API` environment variable.

## Configuration

### Environment Variable

```bash
DEBUG_K8S_API=true    # Enable detailed HTTP/API logging
DEBUG_K8S_API=false   # Disable debug logging (default)
```

### Kubernetes Deployment

Update your deployment YAML files:

**For Aggregator:**
```yaml
env:
- name: DEBUG_K8S_API
  value: "true"  # Enable debug mode
```

**For Collector (DaemonSet):**
```yaml
env:
- name: DEBUG_K8S_API
  value: "true"  # Enable debug mode
```

## What Gets Logged

### Aggregator Debug Logging

When debug mode is enabled, the aggregator logs:

#### 1. Kubernetes Watch Events
All Kubernetes watch events with full object details:
```
DEBUG - K8S API [WATCH] Node: worker-node-1 (event: MODIFIED)
DEBUG - Full Node object data: {
  "metadata": {
    "name": "worker-node-1",
    "annotations": {
      "cluster.x-k8s.io/cluster-name": "my-cluster"
    }
  },
  "spec": {
    "providerID": "aws:///us-east-1a/i-1234567890abcdef0"
  }
}
```

#### 2. Cache Updates
Internal cache modifications:
```
DEBUG - Node cache updated for worker-node-1: {
  "ec2_instance_id": "i-1234567890abcdef0", 
  "cluster_name": "my-cluster"
}
```

#### 3. HTTP-Level Requests
Low-level HTTP requests and responses to the Kubernetes API server:
```
DEBUG - "GET /api/v1/pods HTTP/1.1" 200
DEBUG - Response headers: {
  "content-type": "application/json",
  "x-kubernetes-pf-flowschema-uid": "..."
}
```

### Collector Debug Logging

When debug mode is enabled, the collector logs:

#### 1. HTTP Request/Response Details
All HTTP requests with full response analysis:
```
DEBUG - HTTP [GET] https://127.0.0.1:10250/stats/summary -> 200 OK
DEBUG - Response headers: {'content-type': 'application/json', 'content-length': '12345'}
DEBUG - Response JSON structure: {
  "node": "<dict(5)>",
  "pods": "<list(15)>"
}
```

#### 2. Kubelet Response Analysis
Structured analysis of kubelet statistics:
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

#### 3. EC2 Metadata Service Interactions
IMDSv2 and IMDSv1 request/response logging:
```
DEBUG - HTTP [PUT] http://169.254.169.254/latest/api/token -> 200 OK
DEBUG - HTTP [GET] http://169.254.169.254/latest/meta-data/instance-id -> 200 OK
DEBUG - Response content: i-1234567890abcdef0
```

#### 4. Aggregator Communication
Payload submission and response handling:
```
DEBUG - HTTP [POST] http://aggregator:8888/metrics -> 200 OK
DEBUG - Request data: {
  "timestamp": "2024-01-01T00:00:00Z", 
  "node_name": "worker-node-1",
  "pods": [...]
}
```

## Use Cases

### Aggregator Troubleshooting
- **Pod Discovery Issues**: See exactly which pods are being watched
- **Node Metadata Problems**: Verify cluster annotations and provider IDs
- **PVC/PV Mapping**: Debug storage volume associations  
- **API Connectivity**: Verify communication with Kubernetes API server

### Collector Troubleshooting
- **Kubelet Access Issues**: Verify SSL, authentication, and endpoint connectivity
- **EC2 Metadata Problems**: Debug IMDSv2/v1 token acquisition and metadata retrieval
- **Aggregator Communication**: Monitor payload submission and response handling
- **Network Connectivity**: Trace HTTP-level communication issues

### Performance Analysis
- **Watch Performance**: Monitor Kubernetes API response times
- **HTTP Latency**: Track kubelet and aggregator response times
- **Cache Efficiency**: Observe cache hit/miss patterns
- **Resource Usage**: Track memory impact of full object logging
- **Payload Size**: Monitor metrics payload size and processing time

### Development
- **Schema Validation**: See complete Kubernetes object structures
- **Feature Development**: Understand available metadata fields  
- **API Understanding**: See complete kubelet and aggregator response structures
- **Testing**: Verify correct API interactions and data flow
- **Integration Testing**: Validate end-to-end communication between services

## Performance Impact

⚠️ **Important**: Debug mode significantly increases log volume and memory usage.

### Log Volume
- **Normal**: ~10 log lines per minute
- **Debug**: ~1000+ log lines per minute in active clusters

### Memory Usage
- **Normal**: ~50MB baseline memory
- **Debug**: +100-500MB depending on cluster size

### Network Impact
- No additional network requests (same API calls, just logged)

## Configuration Examples

### Enable for Both Services
```bash
# Enable debug for aggregator
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true

# Enable debug for collector DaemonSet
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true
```

### Enable for Specific Service Only
```bash
# Debug aggregator only
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true

# Debug collector only  
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true
```

### Disable After Troubleshooting
```bash
# Disable debug for both services
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=false
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=false
```

### Production Safety
Always start with debug disabled in production:
```yaml
# Aggregator
env:
- name: DEBUG_K8S_API
  value: "false"  # Safe default

# Collector  
env:
- name: DEBUG_K8S_API
  value: "false"  # Safe default
```

## Log Analysis

### Finding Specific Events

**Aggregator Logs:**
```bash
# Filter for specific resource types
kubectl logs deployment/aggregator -n kube-system | grep "K8S API.*Pod"

# Find cache updates
kubectl logs deployment/aggregator -n kube-system | grep "cache updated"

# Monitor watch events
kubectl logs deployment/aggregator -n kube-system | grep "event:"
```

**Collector Logs:**
```bash
# Filter HTTP requests
kubectl logs daemonset/cost-collector -n kube-system | grep "HTTP"

# Monitor kubelet interactions
kubectl logs daemonset/cost-collector -n kube-system | grep "kubelet"

# Check EC2 metadata requests
kubectl logs daemonset/cost-collector -n kube-system | grep "169.254.169.254"

# Monitor aggregator communication
kubectl logs daemonset/cost-collector -n kube-system | grep "aggregator"
```

### Performance Monitoring
```bash
# Check HTTP response times (both services)
kubectl logs deployment/aggregator -n kube-system | grep "HTTP/1.1"
kubectl logs daemonset/cost-collector -n kube-system | grep "-> [0-9]* "

# Monitor memory usage
kubectl top pods -n kube-system -l app=aggregator
kubectl top pods -n kube-system -l app=cost-collector
```

## Health Check Integration

### Aggregator Health Check
The `/health` endpoint includes debug mode status:

```bash
curl http://aggregator:8888/health
```

Response includes:
```json
{
  "status": "healthy",
  "debug_k8s_api": true,
  "watchers_initialized": {
    "nodes": true,
    "pods": true, 
    "pvcs": true,
    "pvs": true
  },
  "all_watchers_ready": true
}
```

### Collector Health Monitoring
```bash
# Check collector pod status
kubectl get pods -n kube-system -l app=cost-collector

# Monitor collection success rate
kubectl logs daemonset/cost-collector -n kube-system | grep "Pushed.*pod metrics"
```

## Security Considerations

### Sensitive Data Exposure
Debug logs may contain:
- Pod environment variables
- Kubernetes secrets references
- Internal cluster topology
- Node provider IDs and metadata

### Recommendations
1. **Rotate logs frequently** when debug is enabled
2. **Restrict log access** to authorized personnel only
3. **Use debug mode sparingly** in production environments
4. **Monitor log storage usage** to prevent disk exhaustion

## Best Practices

### Development
- Enable debug mode during development and testing
- Use debug logs to understand Kubernetes object relationships
- Validate cache behavior under various conditions

### Production Troubleshooting
1. Enable debug mode only when needed
2. Collect relevant logs quickly
3. Disable debug mode promptly
4. Archive debug logs securely if needed for analysis

### Performance Optimization
- Monitor memory usage with debug enabled
- Use log filtering to reduce noise
- Consider log sampling for very large clusters
- Implement log rotation policies

## Common Debug Scenarios

### Aggregator Issues

**Pod Not Found in Cache:**
```bash
# Enable debug and check pod watch events
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true
kubectl logs deployment/aggregator -n kube-system | grep "Pod.*my-problematic-pod"
```

**EC2 Instance ID Missing:**
```bash
# Check node watch events and provider ID parsing
kubectl logs deployment/aggregator -n kube-system | grep "Node.*provider"
```

**PVC/PV Association Issues:**
```bash
# Monitor PVC and PV watch events
kubectl logs deployment/aggregator -n kube-system | grep -E "(PVC|PV).*volume"
```

### Collector Issues

**Kubelet Access Problems:**
```bash
# Enable debug and check kubelet requests
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(kubelet|10250)"

# Check for authentication errors
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(401|403|Unauthorized)"

# Verify SSL/certificate issues  
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(SSL|certificate|verify)"
```

**EC2 Metadata Service Issues:**
```bash
# Monitor IMDSv2/v1 token acquisition
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(token|169.254.169.254)"

# Check for metadata endpoint timeouts
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(timeout|IMDSv)"
```

**Aggregator Communication Problems:**
```bash
# Monitor payload submission
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(POST.*aggregator|Pushed.*metrics)"

# Check for network connectivity issues
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(connection|timeout|aggregator)"
```

### End-to-End Data Flow Issues

**Metrics Not Reaching Aggregator:**
```bash
# Check collector is pushing
kubectl logs daemonset/cost-collector -n kube-system | grep "Pushed.*pod metrics"

# Check aggregator is receiving
kubectl logs deployment/aggregator -n kube-system | grep "POST /metrics"

# Verify network connectivity
kubectl exec -n kube-system deployment/aggregator -- curl -v http://aggregator:8888/health
```

**Data Processing Pipeline Issues:**
```bash
# Enable debug on both services
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true

# Monitor complete data flow
kubectl logs -f deployment/aggregator -n kube-system &
kubectl logs -f daemonset/cost-collector -n kube-system &

# Wait for one collection cycle, then analyze logs
```

### Performance Troubleshooting

**High Memory Usage:**
```bash
# Check current resource usage
kubectl top pods -n kube-system -l app=aggregator
kubectl top pods -n kube-system -l app=cost-collector

# Enable debug temporarily to identify cause
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true

# Monitor memory during debug
watch kubectl top pods -n kube-system -l app=aggregator
```

**Slow Response Times:**
```bash
# Enable debug to see HTTP timing
kubectl set env deployment/aggregator -n kube-system DEBUG_K8S_API=true
kubectl set env daemonset/cost-collector -n kube-system DEBUG_K8S_API=true

# Monitor response times in logs
kubectl logs deployment/aggregator -n kube-system | grep -E "(HTTP.*->")"
kubectl logs daemonset/cost-collector -n kube-system | grep -E "(HTTP.*->")"
```