#!/usr/bin/env python3
"""
OpenAI Proxy Service - Runs on host to proxy OpenAI API calls for Docker containers
"""
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from openai import OpenAI
import os
import uvicorn
from typing import List, Dict, Any, Optional
import json

app = FastAPI(title="OpenAI Proxy Service")

# OpenAI client with error handling
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ ERROR: OPENAI_API_KEY environment variable not set!")
    exit(1)

try:
    client = OpenAI(api_key=api_key)
    # Test the client
    test_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )
    print("✅ OpenAI client initialized and tested successfully")
except Exception as e:
    print(f"❌ Failed to initialize OpenAI client: {e}")
    exit(1)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 4000

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests for debugging"""
    print(f"📥 {request.method} {request.url.path} from {request.client.host}")
    response = await call_next(request)
    print(f"📤 Response: {response.status_code}")
    return response

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """Proxy OpenAI chat completions - matches OpenAI API format exactly"""
    try:
        print(f"🚀 Proxying OpenAI request:")
        print(f"   Model: {request.model}")
        print(f"   Messages: {len(request.messages)}")
        print(f"   Temperature: {request.temperature}")
        print(f"   Max tokens: {request.max_tokens}")
        
        # Convert messages to OpenAI format
        openai_messages = []
        for msg in request.messages:
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Call OpenAI API exactly like your working example
        response = client.chat.completions.create(
            model=request.model,
            messages=openai_messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        content = response.choices[0].message.content
        print(f"✅ OpenAI response received: {len(content)} characters")
        
        # Return in exact OpenAI API format (matching your working curl example)
        return {
            "id": response.id,
            "object": "chat.completion",
            "created": response.created,
            "model": response.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": response.choices[0].finish_reason
                }
            ],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
        
    except Exception as e:
        print(f"❌ OpenAI API Error: {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI API Error: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "openai-proxy"}

if __name__ == "__main__":
    print("🚀 Starting OpenAI Proxy Service on port 8082...")
    print(f"✅ OpenAI API Key: {os.getenv('OPENAI_API_KEY', 'NOT_SET')[:10]}...")
    uvicorn.run(app, host="0.0.0.0", port=8082)
