#!/bin/bash
echo "🚀 Starting OpenAI Proxy Service..."
# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ ERROR: OPENAI_API_KEY environment variable not set!"
    echo "Please set it in your .env file or export it in your shell"
    exit 1
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
        max_tokens=10
    )
    print('✅ OpenAI connection successful!')
except Exception as e:
    print(f'❌ OpenAI connection failed: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo "🌟 Starting proxy service..."
    python3 openai_proxy.py
else
    echo "❌ Cannot start proxy - OpenAI connection failed"
    exit 1
fi
