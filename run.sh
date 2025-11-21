#!/bin/bash

# Check if GPU is available
if nvidia-smi &> /dev/null; then
    PROFILE="gpu"
    OLLAMA_SERVICE="ollama-gpu"
    echo "GPU detected - using GPU profile"
else
    PROFILE="cpu"
    OLLAMA_SERVICE="ollama-cpu"
    echo "No GPU detected - using CPU profile"
fi

# Start services in detached mode
docker compose --profile $PROFILE up -d --build

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11437/api/tags > /dev/null 2>&1; do
  echo -n "."
  sleep 2
done
echo " Ready!"

# Check if qwen3:8b model exists
if ! docker compose --profile $PROFILE exec -T $OLLAMA_SERVICE ollama list | grep -q "qwen3:8b"; then
    echo "Pulling qwen3:8b model (this may take a few minutes)..."
    docker compose --profile $PROFILE exec -T $OLLAMA_SERVICE ollama pull qwen3:8b
else
    echo "Model qwen3:8b already available"
fi

echo "All services ready! Opening http://localhost:5173"
echo "Press Ctrl+C to stop all services"

# Follow logs
docker compose --profile $PROFILE logs -f