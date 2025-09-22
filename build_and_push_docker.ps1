    docker build -t collector ./collector -f ./collector/Dockerfile
    docker tag collector localhost:5000/collector
    docker push localhost:5000/collector


    docker build -t aggregator ./aggregator -f ./aggregator/Dockerfile
    docker tag aggregator localhost:5000/aggregator
    docker push localhost:5000/aggregator