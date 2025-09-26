# Multi-Architecture Docker Build and Push Script
# Builds and pushes both collector and aggregator images for linux/amd64 and linux/arm64

param(
    [Parameter(Mandatory=$false)]
    [string]$Registry = "unclepaul84",
    
    [Parameter(Mandatory=$false)]
    [string]$Tag = "latest",
    
    [Parameter(Mandatory=$false)]
    [string]$LocalRegistry = "localhost:5000",
    
    [Parameter(Mandatory=$false)]
    [switch]$PushToLocal = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$PushToRegistry = $true,
    
    [Parameter(Mandatory=$false)]
    [switch]$LoadLocal = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$Platforms = "linux/amd64,linux/arm64"
)

Write-Host "Multi-Architecture Docker Build Script" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green

# Display configuration
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Registry: $Registry" -ForegroundColor White
Write-Host "  Tag: $Tag" -ForegroundColor White
Write-Host "  Platforms: $Platforms" -ForegroundColor White
Write-Host "  Push to Registry: $PushToRegistry" -ForegroundColor White
Write-Host "  Push to Local: $PushToLocal" -ForegroundColor White
Write-Host "  Load Local: $LoadLocal" -ForegroundColor White
Write-Host ""

# Check if buildx builder exists and is active
$builderName = "k8s-usage-multiarch"
$activeBuilder = docker buildx ls | Select-String "^\*" | ForEach-Object { $_.ToString().Split()[1] }

if ($activeBuilder -ne $builderName) {
    Write-Host "Setting up multi-architecture builder..." -ForegroundColor Yellow
    
    # Check if our builder exists
    $existingBuilder = docker buildx ls | Select-String $builderName
    if (-not $existingBuilder) {
        Write-Host "Creating multi-platform builder '$builderName'..." -ForegroundColor Cyan
        docker buildx create --name $builderName --driver docker-container --platform $Platforms
    }
    
    # Use the builder
    Write-Host "Switching to multi-platform builder..." -ForegroundColor Cyan
    docker buildx use $builderName
    
    # Bootstrap if needed
    Write-Host "Bootstrapping builder..." -ForegroundColor Cyan
    docker buildx inspect --bootstrap
}

# Function to build and push image
function Build-MultiArchImage {
    param(
        [string]$ImageName,
        [string]$ContextPath,
        [string]$DockerfilePath
    )
    
    Write-Host "Building $ImageName for platforms: $Platforms" -ForegroundColor Cyan
    
    # Prepare build arguments
    $buildArgs = @(
        "buildx", "build"
        "--platform", $Platforms
        "-f", $DockerfilePath
        "-t", "$Registry/k8s-usage-$ImageName`:$Tag"
    )
    
    # Add local registry tag if pushing to local
    if ($PushToLocal) {
        $buildArgs += "-t", "$LocalRegistry/k8s-usage-$ImageName`:$Tag"
    }
    
    # Add push or load flags
    if ($LoadLocal -and $Platforms.Split(",").Count -eq 1) {
        # Can only load single platform builds
        $buildArgs += "--load"
    } elseif ($PushToRegistry -or $PushToLocal) {
        $buildArgs += "--push"
    } else {
        # Build only, don't push or load
        Write-Host "Building without push or load (use --PushToRegistry, --PushToLocal, or --LoadLocal)" -ForegroundColor Yellow
    }
    
    $buildArgs += $ContextPath
    
    Write-Host "Executing: docker $($buildArgs -join ' ')" -ForegroundColor Gray
    
    # Execute build
    $result = & docker @buildArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Successfully built $ImageName" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to build $ImageName" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# Build Collector
Write-Host "`n=== Building Collector ===" -ForegroundColor Yellow
Build-MultiArchImage -ImageName "collector" -ContextPath "./collector" -DockerfilePath "./collector/Dockerfile"

# Build Aggregator  
Write-Host "`n=== Building Aggregator ===" -ForegroundColor Yellow
Build-MultiArchImage -ImageName "aggregator" -ContextPath "./aggregator" -DockerfilePath "./aggregator/Dockerfile"

# Push to local registry if requested and not already pushed during build
if ($PushToLocal -and -not ($PushToRegistry -or $LoadLocal)) {
    Write-Host "`n=== Pushing to Local Registry ===" -ForegroundColor Yellow
    docker push "$LocalRegistry/k8s-usage-collector:$Tag"
    docker push "$LocalRegistry/k8s-usage-aggregator:$Tag"
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Green
Write-Host "Images built for platforms: $Platforms" -ForegroundColor Green

# Show manifest information
if ($PushToRegistry) {
    Write-Host "`nInspecting multi-arch manifests:" -ForegroundColor Cyan
    
    Write-Host "`nCollector manifest:" -ForegroundColor White
    docker buildx imagetools inspect "$Registry/k8s-usage-collector:$Tag"
    
    Write-Host "`nAggregator manifest:" -ForegroundColor White  
    docker buildx imagetools inspect "$Registry/k8s-usage-aggregator:$Tag"
}

Write-Host "`nTo use these images in Kubernetes:" -ForegroundColor Cyan
Write-Host "  - AMD64 nodes will automatically pull linux/amd64 images" -ForegroundColor White
Write-Host "  - ARM64 nodes will automatically pull linux/arm64 images" -ForegroundColor White
Write-Host "  - Update your YAML files to use: $Registry/k8s-usage-collector:$Tag" -ForegroundColor White
Write-Host "  - Update your YAML files to use: $Registry/k8s-usage-aggregator:$Tag" -ForegroundColor White