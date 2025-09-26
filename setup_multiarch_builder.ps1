# Setup Docker Buildx for Multi-Architecture Builds
# This script configures Docker Buildx to support ARM64 and AMD64 builds

Write-Host "Setting up Docker Buildx for multi-architecture builds..." -ForegroundColor Green

# Create a new buildx builder instance with multi-platform support
$builderName = "k8s-usage-multiarch"

# Check if builder already exists
$existingBuilder = docker buildx ls | Select-String $builderName
if ($existingBuilder) {
    Write-Host "Builder '$builderName' already exists. Removing and recreating..." -ForegroundColor Yellow
    docker buildx rm $builderName
}

# Create new multi-platform builder
Write-Host "Creating multi-platform builder '$builderName'..." -ForegroundColor Cyan
docker buildx create --name $builderName --driver docker-container --platform linux/amd64,linux/arm64

# Use the new builder
Write-Host "Switching to multi-platform builder..." -ForegroundColor Cyan
docker buildx use $builderName

# Bootstrap the builder (this will download the buildkit image)
Write-Host "Bootstrapping the builder..." -ForegroundColor Cyan
docker buildx inspect --bootstrap

# Verify the builder supports the required platforms
Write-Host "Verifying platform support..." -ForegroundColor Cyan
docker buildx inspect

Write-Host "Multi-architecture builder setup complete!" -ForegroundColor Green
Write-Host "You can now build images for both linux/amd64 and linux/arm64 platforms." -ForegroundColor Green