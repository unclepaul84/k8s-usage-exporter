# Push single-architecture images to Docker Hub
# For multi-architecture images, use build_multiarch.ps1 with -PushToRegistry

Write-Host "Pushing single-architecture images to Docker Hub..." -ForegroundColor Yellow
Write-Host "Note: For multi-architecture images, use build_multiarch.ps1 -PushToRegistry" -ForegroundColor Cyan

docker push unclepaul84/k8s-usage-collector:latest
docker push unclepaul84/k8s-usage-aggregator:latest

Write-Host "Push to Docker Hub complete!" -ForegroundColor Green