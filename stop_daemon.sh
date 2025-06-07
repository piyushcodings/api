#!/bin/bash

# AutoShopify API Server Stop Script
# Usage: ./stop_daemon.sh [shutdown_key] [port]

SHUTDOWN_KEY=${1:-"default_shutdown_key_123"}
PORT=${2:-6902}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/autoshopify.pid"

echo "=== AutoShopify API Server Shutdown ==="
echo "Port: $PORT"
echo "Script Directory: $SCRIPT_DIR"
echo "======================================="

# Method 1: Try API shutdown (graceful)
echo "Attempting graceful shutdown via API..."
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $SHUTDOWN_KEY" http://localhost:$PORT/shutdown 2>/dev/null)

if [ $? -eq 0 ]; then
    echo "✅ Graceful shutdown initiated via API"
    echo "Response: $RESPONSE"
    sleep 3
else
    echo "⚠️ API shutdown failed or server not responding"
fi

# Method 2: Use PID file if available
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "Found PID file with PID: $PID"
    
    if kill -0 "$PID" 2>/dev/null; then
        echo "Sending TERM signal to PID $PID..."
        kill -TERM "$PID"
        sleep 2
        
        # Check if process is still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Process still running, sending KILL signal..."
            kill -KILL "$PID"
            sleep 1
        fi
        
        # Check final status
        if kill -0 "$PID" 2>/dev/null; then
            echo "❌ Failed to stop process $PID"
        else
            echo "✅ Process $PID stopped successfully"
            rm -f "$PID_FILE"
        fi
    else
        echo "⚠️ Process $PID not running, removing stale PID file"
        rm -f "$PID_FILE"
    fi
else
    echo "No PID file found at $PID_FILE"
fi

# Method 3: Find and kill by process name and port
echo "Searching for processes using port $PORT..."
PROCESSES=$(lsof -ti:$PORT 2>/dev/null || netstat -tlnp 2>/dev/null | grep ":$PORT " | awk '{print $7}' | cut -d'/' -f1)

if [ -n "$PROCESSES" ]; then
    echo "Found processes using port $PORT: $PROCESSES"
    for PID in $PROCESSES; do
        if [ -n "$PID" ] && [ "$PID" != "-" ]; then
            echo "Killing process $PID..."
            kill -TERM "$PID" 2>/dev/null
            sleep 1
            kill -KILL "$PID" 2>/dev/null
        fi
    done
    echo "✅ Processes using port $PORT have been terminated"
else
    echo "No processes found using port $PORT"
fi

# Method 4: Find Python processes with autoshopify
echo "Searching for autoshopify Python processes..."
PYTHON_PIDS=$(pgrep -f "python.*autoshopify")

if [ -n "$PYTHON_PIDS" ]; then
    echo "Found autoshopify Python processes: $PYTHON_PIDS"
    for PID in $PYTHON_PIDS; do
        echo "Killing Python process $PID..."
        kill -TERM "$PID" 2>/dev/null
        sleep 1
        kill -KILL "$PID" 2>/dev/null
    done
    echo "✅ AutoShopify Python processes terminated"
else
    echo "No autoshopify Python processes found"
fi

# Cleanup
rm -f "$PID_FILE" 2>/dev/null

echo ""
echo "=== Shutdown Complete ==="
echo "To verify server is stopped:"
echo "curl http://localhost:$PORT/health"
echo "(Should return connection refused/timeout)" 