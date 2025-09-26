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

The collector logs its startup configuration and metadata collection results:

```
Starting collector with initial delay of 15.34 seconds
Will exit after 5 consecutive failures
EC2 instance ID collection: enabled
EC2 metadata mode: IMDSv2 with IMDSv1 fallback
EC2 metadata token TTL: 21600 seconds
Retrieved EC2 instance ID (IMDSv2): i-1234567890abcdef0
```

Watch the logs to ensure successful metadata collection:

```bash
kubectl logs -f daemonset/cost-collector -n kube-system
```