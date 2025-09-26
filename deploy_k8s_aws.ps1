# Undeploy first
kubectl delete -f k8s/collector.daemonset_aws.yaml --ignore-not-found=true
kubectl delete -f k8s/aggregator_aws.yaml --ignore-not-found=true
# Wait for pods to be terminated
Write-Host "Waiting for pods to be terminated..."
do {
    $pods = kubectl get pods -l app=cost-collector --no-headers 2>$null
    if ($pods) {
        Start-Sleep -Seconds 5
    }
} while ($pods)

Write-Host "Undeployment complete. Proceeding with deployment..."


Write-Host "Waiting for pods to be terminated..."
do {
    $pods = kubectl get pods -l app=aggregator --no-headers 2>$null
    if ($pods) {
        Start-Sleep -Seconds 5
    }
} while ($pods)

Write-Host "Undeployment complete. Proceeding with deployment..."



# Deploy
kubectl apply -f k8s/collector.daemonset_aws.yaml
kubectl apply -f k8s/aggregator_aws.yaml