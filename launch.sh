#!/bin/bash
set -euo pipefail

echo "🚀 Starting Surfer H - Full Stack Application"
echo "=============================================="

# Load environment variables using Python helper
eval "$(uv run python3 load_env.py HAI_API_KEY HAI_MODEL_URL HAI_MODEL_NAME)"
echo ""

# Check if virtual environment exists, create if it doesn't
if [ ! -d ".venv" ]; then
    echo "🐍 Creating virtual environment..."
    uv venv
fi

# Sync dependencies
echo "📦 Syncing dependencies..."
uv sync

# Install backend dependencies
echo "📦 Installing backend dependencies..."
uv pip install -r requirements_server.txt

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo ""
echo "🌐 Starting servers..."
echo "   Backend:  http://localhost:7999"
echo "   Frontend: http://localhost:3000"
echo ""
echo "💡 Open http://localhost:3000 in your browser to use the application"
echo "   Press Ctrl+C to stop both servers"
echo ""

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "🛑 Stopping servers..."
    if [ -n "${BACKEND_PID:-}" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_PID:-}" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    kill "$(jobs -p)" 2>/dev/null || true
    exit 0
}

# Set up trap to cleanup on exit
trap cleanup SIGINT SIGTERM

# Start backend server in background
echo "🔧 Starting backend server..."
uv run python agent_server.py &
BACKEND_PID=$!

# Wait for backend to start and verify it's healthy
echo "⏳ Waiting for backend server to start..."
BACKEND_READY=false
# shellcheck disable=SC2034
for i in {1..30}; do
    if curl -s http://localhost:7999/health > /dev/null 2>&1; then
        BACKEND_READY=true
        break
    fi
    sleep 1
done

if [ "$BACKEND_READY" = false ]; then
    echo "❌ Backend server failed to start or is not responding"
    echo "   Please check the logs above for errors"
    echo "   Common issues:"
    echo "   - Port 7999 already in use"
    echo "   - Python dependencies not installed correctly"
    cleanup
    # shellcheck disable=SC2317
    exit 1
fi

echo "✅ Backend server is running and healthy"

# Start frontend server in background
echo "🎨 Starting frontend server..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait for frontend to start
echo "⏳ Waiting for frontend server to start..."
FRONTEND_READY=false
# shellcheck disable=SC2034
for i in {1..30}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        FRONTEND_READY=true
        break
    fi
    sleep 1
done

if [ "$FRONTEND_READY" = false ]; then
    echo "❌ Frontend server failed to start or is not responding"
    echo "   Please check the logs above for errors"
    cleanup
    # shellcheck disable=SC2317
    exit 1
fi

echo "✅ Frontend server is running and healthy"

# Both servers are confirmed running
echo ""
echo "🎉 Both servers are running successfully!"
echo "   Backend PID: $BACKEND_PID"
echo "   Frontend PID: $FRONTEND_PID"
echo ""
echo "🌐 Application is ready at: http://localhost:3000"
echo ""

# Keep script running and wait for user to interrupt
wait