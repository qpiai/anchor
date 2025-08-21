#!/usr/bin/env python3
"""
Test script to verify OpenAI API connection from inside Docker container
"""
import os
import sys
from openai import OpenAI

def test_openai_connection():
    print("🔍 Testing OpenAI API Connection...")
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    
    print(f"✅ Found API key: {api_key[:7]}...")
    
    try:
        # Create OpenAI client
        client = OpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=2
        )
        
        print("🚀 Making test API call...")
        
        # Make a simple test call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'Hello from OpenAI!' in exactly 5 words."}
            ],
            max_tokens=20,
            temperature=0
        )
        
        result = response.choices[0].message.content
        print(f"✅ OpenAI API Response: {result}")
        print("🎉 OpenAI connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ OpenAI API Error: {type(e).__name__}: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_openai_connection()
    sys.exit(0 if success else 1)
