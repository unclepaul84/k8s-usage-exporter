# Stop and remove existing container if it exists
docker stop registry 2>$null
docker rm registry 2>$null

# Run the new container
docker run -d -p 5000:5000 --restart=always --name registry registry:2