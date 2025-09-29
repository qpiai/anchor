#!/usr/bin/env python3
"""
Anchor Policy Verification MCP Server

This script runs a standalone MCP (Model Context Protocol) server that exposes
Anchor's policy verification functionality to external AI agents.

Usage:
    python run_mcp_server.py [--transport stdio|sse] [--port 8080]

Transport Options:
    --transport stdio: Use STDIO transport (default, for Claude Desktop integration)
    --transport sse: Use SSE (Server-Sent Events) HTTP transport for web integration
    --port: Port for SSE transport (default: 8080)

The server can be integrated with:
- Claude Desktop (STDIO transport)
- VS Code with MCP extensions (STDIO transport)
- Web applications via HTTP (SSE transport)
- Any MCP-compatible AI assistant

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
    OPENAI_API_KEY: OpenAI API key for variable extraction
    ANTHROPIC_API_KEY: Anthropic API key (alternative to OpenAI)
    LOG_LEVEL: Logging level (default: INFO)
"""

import os
import sys
import logging
import argparse
import asyncio
from pathlib import Path

# Add the app directory to Python path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir.parent))

# Import after path setup
from app.mcp_server import mcp

def setup_logging():
    """Setup logging for the MCP server"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Configure logging to stderr only (STDIO requirement for MCP)
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )

    logger = logging.getLogger(__name__)
    logger.info("Anchor MCP Server logging configured")
    return logger

def validate_environment():
    """Validate required environment variables"""
    required_vars = ["DATABASE_URL"]
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}", file=sys.stderr)
        print("Please set these in your .env file or environment", file=sys.stderr)
        sys.exit(1)

    # Check for at least one API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("Warning: No API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY for LLM features", file=sys.stderr)

async def main():
    """Main entry point for the MCP server"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Anchor Policy Verification MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind SSE transport (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    logger = setup_logging()

    logger.info("Starting Anchor Policy Verification MCP Server...")
    logger.info(f"Transport: {args.transport}")
    if args.transport == "sse":
        logger.info(f"Host: {args.host}")
        logger.info(f"Port: {args.port}")
    logger.info("Available tools: list_policies, verify_response, batch_verify, get_policy_info")

    # Load environment variables from .env.docker first, then .env as fallback
    env_docker = Path(__file__).parent / ".env.docker"
    env_file = Path(__file__).parent / ".env"

    from dotenv import load_dotenv

    if env_docker.exists():
        load_dotenv(env_docker)
        logger.info(f"Loaded environment from {env_docker}")

        # For local MCP server connecting to Docker postgres, adjust database URL
        db_url = os.getenv("DATABASE_URL")
        if db_url and "host.docker.internal" in db_url:
            # Replace Docker internal networking with localhost for local connection
            local_db_url = db_url.replace("host.docker.internal", "localhost")
            os.environ["DATABASE_URL"] = local_db_url
            logger.info("Adjusted DATABASE_URL for local connection to Docker postgres")

    elif env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")
    else:
        logger.warning("No .env.docker or .env file found")

    # Validate environment after loading
    validate_environment()

    try:
        # Run the MCP server with appropriate transport
        if args.transport == "sse":
            logger.info(f"MCP Server starting on http://{args.host}:{args.port} with SSE transport...")
            await mcp.run_sse_async(host=args.host, port=args.port)
        else:
            logger.info("MCP Server ready for STDIO connections...")
            await mcp.run_stdio_async()
    except KeyboardInterrupt:
        logger.info("MCP Server shutting down...")
    except Exception as e:
        logger.error(f"MCP Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())