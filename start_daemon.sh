#!/bin/bash

# AutoShopify API Server Startup Script
# Usage: ./start_daemon.sh [port] [shutdown_key] [--install-deps]

PORT=${1:-6902}
SHUTDOWN_KEY=${2:-"autoshopify_secret_$(date +%s)"}
INSTALL_DEPS=${3:-""}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/autoshopify.py"

# Export shutdown key as environment variable
export SHUTDOWN_KEY="$SHUTDOWN_KEY"

echo "=== AutoShopify API Server Daemon Startup ==="
echo "Port: $PORT"
echo "Shutdown Key: $SHUTDOWN_KEY"
echo "Script Directory: $SCRIPT_DIR"
echo "=============================================="

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: autoshopify.py not found in $SCRIPT_DIR"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Check if Python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "⚠️ Python3 not found. Installing..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3 python3-pip
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-pip
    else
        echo "❌ Could not install Python3. Please install manually."
        exit 1
    fi
fi

# Install dependencies on first run or if requested
if [ "$INSTALL_DEPS" = "--install-deps" ] || [ ! -f "$SCRIPT_DIR/.deps_installed" ]; then
    echo "📦 Installing dependencies..."
    cd "$SCRIPT_DIR"
    
    # Install Python dependencies
    python3 autoshopify.py --install-deps
    
    # Install system dependencies if requested with sudo
    if [ "$INSTALL_DEPS" = "--install-system-deps" ]; then
        echo "🐧 Installing system dependencies (requires sudo)..."
        sudo python3 autoshopify.py --install-system-deps
    fi
    
    echo "✅ Dependencies installation complete"
fi

# Method 1: Using nohup (recommended for VPS)
echo "Starting server using nohup..."
cd "$SCRIPT_DIR"
nohup python3 autoshopify.py --daemon --port "$PORT" > logs/startup.log 2>&1 &
SERVER_PID=$!

# Wait a moment to check if server started successfully
sleep 3

# Check if the process is still running
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "✅ Server started successfully!"
    echo "PID: $SERVER_PID"
    echo "Port: $PORT"
    echo "Logs: $SCRIPT_DIR/logs/"
    echo ""
    echo "To check server status:"
    echo "curl http://localhost:$PORT/health"
    echo ""
    echo "To stop the server:"
    echo "curl -X POST -H 'Authorization: Bearer $SHUTDOWN_KEY' http://localhost:$PORT/shutdown"
    echo "OR"
    echo "kill $SERVER_PID"
    echo "OR"
    echo "kill \$(cat autoshopify.pid)"
    echo ""
    echo "To view logs:"
    echo "tail -f logs/autoshopify.log"
    echo "tail -f logs/autoshopify_error.log"
    echo ""
    echo "🎉 AutoShopify API is now running in the background!"
    echo "Even if you logout from SSH, the server will continue running."
else
    echo "❌ Server failed to start. Check logs/startup.log for details."
    echo "Startup log content:"
    echo "===================="
    cat logs/startup.log
    echo "===================="
    exit 1
fi 