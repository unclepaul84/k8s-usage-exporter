# Kubernetes Deployment Configurations

This directory contains Kubernetes deployment configurations for the k8s-usage-exporter components.

## Multi-Architecture Support

The k8s-usage-exporter images support both AMD64 and ARM64 architectures:
- Images automatically work on Intel/AMD and ARM-based Kubernetes nodes
- No configuration changes needed - Kubernetes pulls the correct architecture automatically
- Supports AWS Graviton, Apple Silicon, and traditional x86 hardware

For building multi-architecture images, see [MULTIARCH_BUILD_GUIDE.md](../MULTIARCH_BUILD_GUIDE.md).

## Files

### `aggregator.yaml`
Basic aggregator deployment configured to use MinIO from the iceberg docker-compose setup.

**MinIO Configuration:**
- Endpoint: `http://minio:9000`
- Bucket: `warehouse`
- Access Key: `minio`
- Secret Key: `minio123`

**Note:** This configuration includes credentials in plain text. Use this for development/testing only.

### `aggregator-with-minio-secrets.yaml`
Production-ready aggregator deployment that uses Kubernetes secrets for MinIO credentials.

**Features:**
- MinIO credentials stored in Kubernetes secrets
- Base64 encoded sensitive data
- Same MinIO configuration as iceberg setup
- More secure for production environments

### `collector.daemonset.yaml`
DaemonSet configuration for the metrics collector that runs on each node.

## Deployment Options

### Option 1: Basic Deployment (Development)
```bash
kubectl apply -f aggregator.yaml
kubectl apply -f collector.daemonset.yaml
```

### Option 2: Secure Deployment (Production)
```bash
kubectl apply -f aggregator-with-minio-secrets.yaml
kubectl apply -f collector.daemonset.yaml
```

## MinIO Integration

Both aggregator configurations are set up to work with the MinIO instance from the iceberg docker-compose setup:

1. **Bucket**: Uses the `warehouse` bucket (same as iceberg catalog)
2. **Endpoint**: Points to `http://minio:9000`
3. **Credentials**: Uses the same access key and secret as iceberg configuration
4. **Object Path**: Stores metrics at `k8s-metrics/{cluster_name}/{date}/`

This allows the k8s usage metrics to be stored alongside iceberg data for unified analytics.

## Prerequisites

Before deploying the aggregator, ensure:

1. MinIO is running and accessible at `http://minio:9000`
2. The `warehouse` bucket exists in MinIO
3. The MinIO credentials (`minio`/`minio123`) are valid

## Monitoring

Check aggregator logs to verify MinIO connectivity:
```bash
kubectl logs -n kube-system deployment/aggregator
```

Expected log messages:
- `Using custom S3 endpoint: http://minio:9000`
- `S3 client initialized successfully for bucket: warehouse with endpoint http://minio:9000`
- `Successfully uploaded metrics to S3: s3://warehouse/k8s-metrics/...`

## Security Considerations

- **Development**: The basic `aggregator.yaml` is suitable for development environments
- **Production**: Use `aggregator-with-minio-secrets.yaml` for production deployments
- **Credentials**: Consider rotating MinIO credentials regularly
- **Network**: Ensure proper network policies restrict access to MinIO