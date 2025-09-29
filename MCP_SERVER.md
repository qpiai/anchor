# Anchor MCP Server

The Anchor MCP (Model Context Protocol) Server exposes policy verification functionality to external AI agents, allowing them to verify responses against your indexed and compiled policies.

## Overview

The MCP server provides a standardized interface for AI assistants to:
- List available compiled policies
- Verify question-answer pairs against policies
- Perform batch verification of multiple scenarios
- Get detailed policy information

## Installation

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   The `fastmcp==0.4.0` dependency is included in requirements.txt.

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env and set your database URL and API keys
   ```

3. **Ensure Database is Running**
   ```bash
   docker-compose up -d postgres
   ```

4. **Verify Policies are Compiled**
   Make sure you have policies uploaded and compiled through the main Anchor application.

## Running the MCP Server

### Option 1: Docker Compose 

The MCP server is included in the `docker-compose.yml` configuration and runs as a separate service on port 8787 using SSE (Server-Sent Events) transport:

```bash
# Start all services including MCP server
docker-compose up -d

# Or start only the MCP server (requires db to be running)
docker-compose up -d mcp-server
```

**Note:** If you don't need the MCP server functionality, you can comment out the `mcp-server` service in `docker-compose.yml` to save resources.

The Docker Compose MCP server:
- Uses the same Docker image as the main backend (`ishantkohar/anchor-backend`)
- Runs on port 8787 with SSE transport for HTTP-based access
- Shares the same database and environment configuration (`.env.docker`)
- Automatically restarts unless stopped
- Includes health checks for reliability

**Can MCP server run without the backend service?**

Yes! The MCP server can run independently without the `backend` service running. It only requires:
- ✅ Database (`db` service) to be running
- ✅ Policies already uploaded and compiled in the database
- ✅ API keys configured for variable extraction

You can run just the MCP server and database:
```bash
# Start only database and MCP server
docker-compose up -d db mcp-server
```

The backend service is only needed for:
- Uploading new documents/policies
- Compiling policies into Z3 constraints
- Managing policies through the web UI/API

Once policies are compiled, the MCP server can verify responses independently.

### Option 2: Standalone Mode (Development/Local)

For development or integration with desktop AI assistants (like Claude Desktop), run the MCP server manually:

```bash
# Default: STDIO transport (for Claude Desktop, local AI assistants)
python run_mcp_server.py

# With explicit arguments
python run_mcp_server.py --transport stdio

# SSE transport for HTTP access
python run_mcp_server.py --transport sse --host 0.0.0.0 --port 8080

# SSE on a different port
python run_mcp_server.py --transport sse --host localhost --port 8787
```

**Available Command-Line Arguments:**

- `--transport`: Transport protocol to use
  - `stdio` (default): For desktop AI assistants (Claude Desktop, etc.)
  - `sse`: For HTTP-based integrations (web apps, Cursor with HTTP)
  
- `--host`: Host to bind for SSE transport (default: `0.0.0.0`)
  - `0.0.0.0`: Accept connections from any network interface
  - `localhost` or `127.0.0.1`: Only local connections
  
- `--port`: Port number for SSE transport (default: `8080`)
  - Example: `8787` (used in Docker Compose)

The STDIO transport is ideal for direct integration with AI assistant applications, while SSE transport provides HTTP-based access for web integrations.

### Environment Variables

The MCP server uses the same configuration as the main Anchor application:

- `DATABASE_URL`: PostgreSQL connection string (required)
- `OPENAI_API_KEY`: OpenAI API key for variable extraction
- `ANTHROPIC_API_KEY`: Alternative to OpenAI (optional)
- `LOG_LEVEL`: Logging verbosity (default: INFO)

## Integration with AI Assistants

The MCP server supports two transport modes:
- **STDIO**: For local desktop applications (Claude Desktop, etc.)
- **SSE (Server-Sent Events)**: For HTTP-based integrations (Cursor, web applications)

### Cursor IDE (SSE Transport)

When running the MCP server via Docker Compose, it's accessible via SSE on port 8787. Add this configuration to your Cursor MCP settings (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "anchor": {
      "transport": "sse",
      "url": "http://localhost:8787/sse"
    }
  }
}
```

After adding the configuration, restart Cursor to connect to the Anchor MCP server.

### Claude Desktop (STDIO Transport)

For local STDIO integration, add this configuration to your Claude Desktop MCP settings:

```json
{
  "mcpServers": {
    "anchor-verification": {
      "command": "python",
      "args": ["/path/to/anchor/run_mcp_server.py"],
      "cwd": "/path/to/anchor"
    }
  }
}
```

### VS Code with MCP Extensions

1. Install an MCP extension for VS Code
2. Configure the server:
   - **For STDIO**: Point to `/path/to/anchor/run_mcp_server.py`
   - **For SSE**: Use `http://localhost:8787/sse` (requires Docker Compose)
3. Restart VS Code

### Custom Integration

**STDIO Transport:**
```python
from mcp import Client

# Connect to the server
client = Client("python", ["/path/to/anchor/run_mcp_server.py"])
```

**SSE Transport:**
```python
import httpx

# Connect to SSE endpoint
async with httpx.AsyncClient() as client:
    async with client.stream("GET", "http://localhost:8787/sse") as response:
        async for line in response.aiter_lines():
            # Handle SSE events
            pass
```

## Available Tools

### 1. `list_policies`

Lists all available compiled policies that can be used for verification.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "policies": [
    {
      "id": "uuid-here",
      "name": "Employee Vacation Policy",
      "description": "Policy for employee vacation requests",
      "domain": "hr",
      "created_at": "2024-01-01T00:00:00",
      "variable_count": 5,
      "rule_count": 3
    }
  ],
  "total_count": 1
}
```

### 2. `verify_response`

Verifies a single question-answer pair against a policy.

**Parameters:**
- `policy_id` (string): UUID of the policy to verify against
- `question` (string): The question being asked
- `answer` (string): The answer to verify

**Returns:**
```json
{
  "success": true,
  "result": "valid",
  "explanation": "✅ All policy rules are satisfied. The scenario is valid according to the policy.",
  "extracted_variables": {
    "employee_type": "full_time",
    "requested_days": 10
  },
  "suggestions": []
}
```

**Possible Results:**
- `valid`: The scenario complies with the policy
- `invalid`: The scenario violates one or more policy rules
- `needs_clarification`: Missing information required for verification
- `error`: Technical error during verification

### 3. `batch_verify`

Verifies multiple question-answer pairs against a single policy in batch.

**Parameters:**
- `policy_id` (string): UUID of the policy to verify against
- `qa_pairs` (array): List of objects with `question` and `answer` keys

**Returns:**
```json
{
  "success": true,
  "results": [
    {
      "index": 0,
      "question": "Can I take 10 days vacation?",
      "answer": "Yes, as a full-time employee",
      "result": "valid",
      "explanation": "Policy allows full-time employees up to 15 days",
      "extracted_variables": {"employee_type": "full_time", "requested_days": 10},
      "suggestions": []
    }
  ],
  "summary": {
    "total": 1,
    "valid": 1,
    "invalid": 0,
    "needs_clarification": 0,
    "errors": 0
  }
}
```

### 4. `get_policy_info`

Gets detailed information about a policy including variables, rules, and examples.

**Parameters:**
- `policy_id` (string): UUID of the policy to get information for

**Returns:**
```json
{
  "success": true,
  "policy": {
    "id": "uuid-here",
    "name": "Employee Vacation Policy",
    "description": "Policy for managing employee vacation requests",
    "domain": "hr",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "is_compiled": true,
    "compiled_at": "2024-01-01T00:00:00",
    "variables": [
      {
        "name": "employee_type",
        "type": "enum",
        "description": "Type of employment",
        "possible_values": ["full_time", "part_time"],
        "is_mandatory": true
      }
    ],
    "rules": [
      {
        "id": "vacation_limit",
        "description": "Full-time employees can take up to 15 days",
        "condition": "employee_type == 'full_time' AND requested_days <= 15",
        "conclusion": "valid"
      }
    ],
    "examples": []
  }
}
```

## Usage Examples

### Example 1: List Available Policies

**AI Agent Query:** "What policies are available for verification?"

**MCP Tool Call:**
```json
{
  "tool": "list_policies"
}
```

### Example 2: Verify a Vacation Request

**AI Agent Query:** "Can a full-time employee take 12 days of vacation with 2 weeks notice?"

**MCP Tool Call:**
```json
{
  "tool": "verify_response",
  "parameters": {
    "policy_id": "policy-uuid-here",
    "question": "Can a full-time employee take 12 days of vacation?",
    "answer": "Yes, with 2 weeks advance notice provided"
  }
}
```

### Example 3: Batch Verification

**AI Agent Query:** "Verify these vacation scenarios against the HR policy"

**MCP Tool Call:**
```json
{
  "tool": "batch_verify",
  "parameters": {
    "policy_id": "policy-uuid-here",
    "qa_pairs": [
      {
        "question": "Can I take 5 days off?",
        "answer": "Yes, as a part-time employee"
      },
      {
        "question": "Can I take 20 days off?",
        "answer": "Yes, as a full-time employee"
      }
    ]
  }
}
```

## Error Handling

All tools return a `success` field indicating whether the operation completed successfully. When `success` is `false`, an `error` field provides details about what went wrong.

Common error scenarios:
- **Policy not found**: Invalid policy ID provided
- **Policy not compiled**: Policy exists but hasn't been compiled to Z3 constraints
- **Variable extraction failed**: Issues parsing the question/answer pair
- **Z3 verification failed**: Technical error in the constraint solver
- **Database connection error**: Unable to connect to the database

## Troubleshooting

### Server Won't Start

1. **Check dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify environment variables:**
   ```bash
   echo $DATABASE_URL
   echo $OPENAI_API_KEY
   ```

3. **Check database connectivity:**
   ```bash
   docker-compose logs postgres
   ```

### No Policies Available

1. **Upload policies through the main Anchor application:**
   ```bash
   curl -X POST "http://localhost:9066/api/v1/documents/upload" \
     -F "file=@policy.pdf" -F "domain=hr"
   ```

2. **Compile policies:**
   ```bash
   curl -X POST "http://localhost:9066/api/v1/policies/{id}/compile"
   ```

### Verification Errors

1. **Check policy compilation status in the main application**
2. **Verify the policy has the required variables for your Q&A pair**
3. **Check logs for detailed error messages**

## Security Considerations

- **Read-Only Access**: The MCP server only provides verification functionality, no data modification
- **Database Access**: Uses the same database credentials as the main application
- **API Keys**: Requires API keys only for variable extraction (LLM processing)
- **Network Isolation**: Runs locally via STDIO, no network exposure by default

## Development

### Adding New Tools

To add new verification tools:

1. **Define the tool function in `app/mcp_server.py`:**
   ```python
   @mcp.tool
   def my_new_tool(request: MyRequestModel) -> Dict[str, Any]:
       # Implementation here
       pass
   ```

2. **Add appropriate Pydantic models for type safety**
3. **Update this documentation with the new tool**

### Testing

Test the MCP server manually:

```bash
# Start the server
python run_mcp_server.py

# In another terminal, test with echo
echo '{"method": "tools/list"}' | python run_mcp_server.py
```

## Integration with Main Application

The MCP server is designed to run alongside the main Anchor FastAPI application:

- **Shared Database**: Both use the same PostgreSQL database
- **Shared Services**: MCP server reuses existing verification and variable extraction services
- **Independent Operation**: Can run simultaneously without conflicts
- **Same Configuration**: Uses the same `.env` file for consistency

This allows external AI agents to verify responses while the main application continues to handle policy management, document upload, and compilation.