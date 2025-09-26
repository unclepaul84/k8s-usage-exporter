# Multi-Architecture Docker Build Guide

This guide explains how to build and deploy container images that support both AMD64 (x86_64) and ARM64 architectures.

## Overview

The k8s-usage-exporter project now supports multi-architecture container builds, allowing the same images to run on:
- **AMD64/x86_64**: Traditional Intel/AMD processors
- **ARM64/AArch64**: ARM processors (AWS Graviton, Apple Silicon, Raspberry Pi, etc.)

## Prerequisites

1. **Docker with Buildx support** (Docker Desktop 19.03+ or Docker Engine 19.03+)
2. **Docker Buildx plugin** (usually included with modern Docker installations)
3. **Multi-platform builder** (set up automatically by our scripts)

## Build Scripts

### Quick Start

For most users, use these convenience scripts:

```powershell
# Build and push multi-arch images to Docker Hub
.\build_and_push_multiarch.ps1

# Build multi-arch images for local development
.\build_local_multiarch.ps1
```

### Detailed Build Options

For more control, use the main multi-arch build script:

```powershell
# Build and push to Docker Hub (default)
.\build_multiarch.ps1

# Build specific platforms
.\build_multiarch.ps1 -Platforms "linux/amd64,linux/arm64"

# Build for ARM64 only
.\build_multiarch.ps1 -Platforms "linux/arm64"

# Build with custom registry and tag
.\build_multiarch.ps1 -Registry "myregistry" -Tag "v1.0.0"

# Build and push to local registry
.\build_multiarch.ps1 -PushToLocal -LocalRegistry "localhost:5000"

# Build without pushing (just validate)
.\build_multiarch.ps1 -PushToRegistry:$false
```

### Traditional Single-Architecture Builds

For local development or CI/CD that doesn't need multi-arch:

```powershell
# Traditional builds (current platform only)
.\build_and_push_docker.ps1

# Push existing single-arch images
.\push_docker_hub.ps1
```

## Script Reference

| Script | Purpose | Multi-Arch | Recommended Use |
|--------|---------|------------|-----------------|
| `setup_multiarch_builder.ps1` | Initialize buildx | N/A | One-time setup |
| `build_multiarch.ps1` | Main multi-arch build | ✅ | Production builds |
| `build_and_push_multiarch.ps1` | Quick multi-arch to Docker Hub | ✅ | CI/CD, releases |
| `build_local_multiarch.ps1` | Multi-arch local dev | ✅ | Local testing |
| `build_and_push_docker.ps1` | Traditional builds | ❌ | Legacy/simple builds |
| `push_docker_hub.ps1` | Push existing images | ❌ | Single-arch pushes |

## Setup Instructions

### 1. Initialize Multi-Architecture Builder

Run this once to set up Docker Buildx:

```powershell
.\setup_multiarch_builder.ps1
```

This creates a builder instance named `k8s-usage-multiarch` that supports both AMD64 and ARM64 platforms.

### 2. Build Multi-Architecture Images

```powershell
# Build and push to Docker Hub
.\build_and_push_multiarch.ps1
```

### 3. Update Kubernetes Deployments

No changes needed! Kubernetes automatically pulls the correct architecture:

```yaml
# This works for both AMD64 and ARM64 nodes
image: unclepaul84/k8s-usage-collector:latest
image: unclepaul84/k8s-usage-aggregator:latest
```

## Architecture-Specific Considerations

### Collector Service

The collector works identically on both architectures:
- Python requests library is pure Python (no compiled dependencies)
- Kubernetes API calls work the same way
- EC2 metadata service (IMDSv2) works on both Intel and Graviton instances

### Aggregator Service

The aggregator includes some packages with native dependencies:
- **pandas**: Has optimized binaries for both architectures
- **pyarrow**: Provides ARM64 wheels
- **gunicorn**: Pure Python, works everywhere

All dependencies automatically use the correct architecture-specific wheels during build.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Multi-Arch
on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v2
      
    - name: Login to Docker Hub
      uses: docker/login-action@v2
      with:
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_TOKEN }}
        
    - name: Build and push
      run: |
        # Setup builder
        docker buildx create --name multiarch --platform linux/amd64,linux/arm64
        docker buildx use multiarch
        
        # Build collector
        docker buildx build --platform linux/amd64,linux/arm64 \\
          -t unclepaul84/k8s-usage-collector:latest \\
          -f ./collector/Dockerfile ./collector --push
          
        # Build aggregator  
        docker buildx build --platform linux/amd64,linux/arm64 \\
          -t unclepaul84/k8s-usage-aggregator:latest \\
          -f ./aggregator/Dockerfile ./aggregator --push
```

## Verification

### Check Multi-Architecture Manifest

```powershell
# Inspect the manifest to see available architectures
docker buildx imagetools inspect unclepaul84/k8s-usage-collector:latest
docker buildx imagetools inspect unclepaul84/k8s-usage-aggregator:latest
```

### Test on Different Architectures

Deploy to a mixed cluster:
- AMD64 nodes will automatically pull `linux/amd64` images
- ARM64 nodes will automatically pull `linux/arm64` images
- No configuration changes needed

## Troubleshooting

### Builder Issues

If you get buildx errors:

```powershell
# Remove and recreate builder
docker buildx rm k8s-usage-multiarch
.\setup_multiarch_builder.ps1
```

### Platform-Specific Issues

```powershell
# Build single platform for debugging
.\build_multiarch.ps1 -Platforms "linux/amd64" -LoadLocal

# Or build ARM64 only
.\build_multiarch.ps1 -Platforms "linux/arm64" -PushToRegistry
```

### Manifest Inspection

```powershell
# Check what platforms are available
docker manifest inspect unclepaul84/k8s-usage-collector:latest
```

## Performance Considerations

### Build Time
- Multi-arch builds take longer (building for 2 platforms)
- Use buildx cache for faster rebuilds
- Consider building single-arch for development

### Runtime Performance
- ARM64 images may have different performance characteristics
- Test both architectures in your environment
- Monitor resource usage on different node types

## Security

### Non-Root Containers
Both Dockerfiles now use non-root users:
- Collector runs as user `collector`
- Aggregator runs as user `aggregator`

### Image Scanning
Scan both architectures for vulnerabilities:
```bash
# Scan AMD64 version
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \\
  aquasec/trivy image --platform linux/amd64 unclepaul84/k8s-usage-collector:latest

# Scan ARM64 version  
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \\
  aquasec/trivy image --platform linux/arm64 unclepaul84/k8s-usage-collector:latest
```

## Migration from Single-Architecture

1. **No Kubernetes changes needed** - existing deployments work unchanged
2. **Rebuild images** using new multi-arch scripts
3. **Verify deployment** on both architecture types
4. **Update CI/CD** to use multi-arch builds

The multi-architecture images are backward compatible with single-architecture deployments.