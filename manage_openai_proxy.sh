#!/bin/bash

PROXY_PID_FILE="/tmp/openai_proxy.pid"
PROXY_LOG_FILE="openai_proxy.log"
PROXY_PORT=8082

function start_proxy() {
    if [ -f "$PROXY_PID_FILE" ] && kill -0 $(cat "$PROXY_PID_FILE") 2>/dev/null; then
        echo "✅ OpenAI proxy is already running (PID: $(cat $PROXY_PID_FILE))"
        return 0
    fi
    
    echo "🚀 Starting OpenAI proxy service..."
    
    # Check if virtual environment exists and activate it
    if [ -d "test_env" ]; then
        source test_env/bin/activate
        echo "✅ Activated virtual environment"
    fi
    
    # Load environment variables from .env file
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    
    # Check if OPENAI_API_KEY is set
    if [ -z "$OPENAI_API_KEY" ]; then
        echo "❌ ERROR: OPENAI_API_KEY environment variable not set!"
        echo "Please set it in your .env file or export it in your shell"
        return 1
    fi
    
    # Test OpenAI connection first
    echo "🔍 Testing OpenAI connection..."
    python3 -c "
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
try:
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': 'Hello'}],
        max_tokens=5
    )
    print('✅ OpenAI connection successful!')
except Exception as e:
    print(f'❌ OpenAI connection failed: {e}')
    exit(1)
"
    
    if [ $? -ne 0 ]; then
        echo "❌ Cannot start proxy - OpenAI connection failed"
        return 1
    fi
    
    # Start the proxy in background
    nohup python3 openai_proxy.py > "$PROXY_LOG_FILE" 2>&1 &
    PROXY_PID=$!
    echo $PROXY_PID > "$PROXY_PID_FILE"
    
    # Wait a moment and check if it's running
    sleep 3
    if kill -0 $PROXY_PID 2>/dev/null; then
        echo "✅ OpenAI proxy started successfully (PID: $PROXY_PID)"
        echo "🌐 Proxy URL: http://localhost:$PROXY_PORT"
        echo "📄 Logs: $PROXY_LOG_FILE"
        
        # Test proxy health
        if curl -s http://localhost:$PROXY_PORT/health > /dev/null; then
            echo "🎉 Proxy health check passed!"
        else
            echo "⚠️  Proxy started but health check failed"
        fi
    else
        echo "❌ Failed to start proxy"
        rm -f "$PROXY_PID_FILE"
        return 1
    fi
}

function stop_proxy() {
    if [ -f "$PROXY_PID_FILE" ]; then
        PID=$(cat "$PROXY_PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo "🛑 Stopping OpenAI proxy (PID: $PID)..."
            kill $PID
            rm -f "$PROXY_PID_FILE"
            echo "✅ Proxy stopped"
        else
            echo "⚠️  Proxy PID file exists but process not running"
            rm -f "$PROXY_PID_FILE"
        fi
    else
        echo "⚠️  Proxy is not running"
    fi
}

function status_proxy() {
    if [ -f "$PROXY_PID_FILE" ] && kill -0 $(cat "$PROXY_PID_FILE") 2>/dev/null; then
        PID=$(cat "$PROXY_PID_FILE")
        echo "✅ OpenAI proxy is running (PID: $PID)"
        echo "🌐 URL: http://localhost:$PROXY_PORT"
        echo "📄 Logs: $PROXY_LOG_FILE"
        
        # Test health
        if curl -s http://localhost:$PROXY_PORT/health > /dev/null; then
            echo "🎉 Health check: PASSED"
        else
            echo "❌ Health check: FAILED"
        fi
    else
        echo "❌ OpenAI proxy is not running"
        [ -f "$PROXY_PID_FILE" ] && rm -f "$PROXY_PID_FILE"
    fi
}

function restart_proxy() {
    echo "🔄 Restarting OpenAI proxy..."
    stop_proxy
    sleep 2
    start_proxy
}

case "$1" in
    start)
        start_proxy
        ;;
    stop)
        stop_proxy
        ;;
    restart)
        restart_proxy
        ;;
    status)
        status_proxy
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "  start   - Start the OpenAI proxy service"
        echo "  stop    - Stop the OpenAI proxy service"
        echo "  restart - Restart the OpenAI proxy service"
        echo "  status  - Check proxy status and health"
        exit 1
        ;;
esac
