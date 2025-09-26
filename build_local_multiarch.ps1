# Build multi-arch images for local development
# This script builds images for both architectures but only loads the current platform locally

Write-Host "Building multi-architecture images for local development..." -ForegroundColor Green

# Get current platform
$currentPlatform = "linux/amd64"  # Default to amd64, could detect actual platform if needed

# Build for current platform only and load locally
& .\build_multiarch.ps1 -Registry "unclepaul84" -Tag "latest" -Platforms $currentPlatform -LoadLocal -PushToRegistry:$false

Write-Host "Local multi-arch development build complete!" -ForegroundColor Green
Write-Host "Image loaded locally for platform: $currentPlatform" -ForegroundColor Cyan