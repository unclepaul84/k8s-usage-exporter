# Quick multi-arch build and push to Docker Hub
# This is a convenience script that calls build_multiarch.ps1 with common settings

Write-Host "Building and pushing multi-architecture images to Docker Hub..." -ForegroundColor Green

# Execute the main multi-arch build script
& .\build_multiarch.ps1 -Registry "unclepaul84" -Tag "latest" -PushToRegistry

Write-Host "Multi-arch build and push to Docker Hub complete!" -ForegroundColor Green
Write-Host "Images are now available for both AMD64 and ARM64 architectures." -ForegroundColor Cyan