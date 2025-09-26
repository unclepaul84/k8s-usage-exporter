 

    docker build -t collector ./collector -f ./collector/Dockerfile -t localhost:5000/collector -t unclepaul84/k8s-usage-collector:latest

    docker push localhost:5000/collector

    docker build -t aggregator ./aggregator -f ./aggregator/Dockerfile -t localhost:5000/aggregator -t unclepaul84/k8s-usage-aggregator:latest

    docker push localhost:5000/aggregator