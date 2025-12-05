#!/bin/bash

echo "=== Video Search Tool Installation Script ==="
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required system dependencies
echo "Checking system dependencies..."

# Check for FFmpeg
if ! command_exists ffmpeg; then
    echo "ERROR: FFmpeg is not installed. Please install FFmpeg first:"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
    echo "  macOS: brew install ffmpeg"
    echo "  Windows: Download from https://ffmpeg.org/download.html"
    exit 1
fi

# Check for Node.js (for frontend)
if ! command_exists node; then
    echo "WARNING: Node.js is not installed. Frontend will not work without it."
    echo "  Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt install nodejs"
    echo "  macOS: brew install node"
    echo "  Windows: Download from https://nodejs.org/"
fi

echo "System dependencies check completed."
echo ""

# Install/Update Ollama
echo "Installing/Updating Ollama..."
if command_exists ollama; then
    echo "Ollama is already installed."
else
    curl -fsSL https://ollama.ai/install.sh | sh
fi

# Function to check if Ollama is serving
check_ollama_serving() {
    curl -s http://localhost:11437/api/tags >/dev/null 2>&1
}

# Function to start Ollama service
start_ollama() {
    echo "Starting Ollama service on port 11437..."
    OLLAMA_HOST=0.0.0.0:11437 ollama serve &
    OLLAMA_PID=$!
    
    # Wait for Ollama to start (max 30 seconds)
    echo "Waiting for Ollama to start..."
    for i in {1..30}; do
        if check_ollama_serving; then
            echo "Ollama is now serving on localhost:11437"
            return 0
        fi
        sleep 1
    done
    
    echo "Warning: Ollama failed to start or is taking longer than expected"
    return 1
}

# Ensure Ollama is serving
echo "Checking if Ollama is serving..."
if check_ollama_serving; then
    echo "Ollama is already serving."
else
    start_ollama
fi
echo ""

# Backend setup
echo "Setting up backend..."
cd backend || exit 1

read -p "Install the Video Search backend in a virtual environment? (Type 'y' to agree, or leave blank to skip. Press Enter): " VENV_CHOICE
if [[ $VENV_CHOICE == [yY] ]]; then
    echo "Creating virtual environment..."
    uv venv .venv
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

echo "Installing backend dependencies..."
uv sync

echo ""

# Frontend setup
echo "Setting up frontend..."
cd ../frontend || exit 1

if command_exists npm; then
    echo "Installing frontend dependencies..."
    npm install
else
    echo "Skipping frontend setup (Node.js not available)"
fi

echo ""

# Download Ollama model
echo "Downloading Ollama model..."
cd .. || exit 1

if check_ollama_serving; then
    echo "Ollama is serving, downloading model..."
    ollama pull qwen3:8b || echo "Failed to download model. You can manually download it later with: ollama pull qwen3:8b"
else
    echo "Ollama is not serving. Please start Ollama manually and download a model with: ollama pull qwen3:8b"
fi

echo ""
echo "=== Installation Complete! ==="
echo ""
echo "To start the application:"
echo "1. Start backend: cd backend && source .venv/bin/activate && python -m app.main"
echo "2. Start frontend: cd frontend && npm run dev"
echo "3. Or use Docker: ./run.sh"
echo ""
echo "The application will be available at:"
echo "- Frontend: http://localhost:5173"
echo "- Backend API: http://localhost:9091"
echo ""
echo "Note: Ollama will continue running in the background. To stop it later, run: pkill ollama"
