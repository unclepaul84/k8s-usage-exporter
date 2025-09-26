# Traditional single-architecture builds for local development
# For multi-architecture builds, use build_multiarch.ps1 instead

Write-Host "Building single-architecture images for local development..." -ForegroundColor Yellow
Write-Host "Note: For multi-architecture builds (ARM64 + AMD64), use build_multiarch.ps1" -ForegroundColor Cyan

# Build collector
Write-Host "Building collector..." -ForegroundColor Green
docker build -t collector ./collector -f ./collector/Dockerfile
docker tag collector localhost:5000/collector
docker tag collector unclepaul84/k8s-usage-collector:latest

# Build aggregator  
Write-Host "Building aggregator..." -ForegroundColor Green
docker build -t aggregator ./aggregator -f ./aggregator/Dockerfile
docker tag aggregator localhost:5000/aggregator
docker tag aggregator unclepaul84/k8s-usage-aggregator:latest

# Push to local registry
Write-Host "Pushing to local registry..." -ForegroundColor Green
docker push localhost:5000/collector
docker push localhost:5000/aggregator

Write-Host "Single-architecture build complete!" -ForegroundColor Green