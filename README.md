# Automated Reasoning Backend

Multi-agent AI system for autonomous policy generation, formal verification, and automated reasoning checks.

## 🎯 Overview

This system implements AWS Bedrock Guardrails-style automated reasoning with autonomous policy generation capabilities. It uses multiple LLM agents to generate domain-specific policies from documents, compiles them to formal Z3 constraints, and provides mathematically verified validation of user queries.

## 🏗️ Architecture

```
Document Upload → Policy Generation → Manual Review/Edit → Z3 Compilation → Verification Engine
```

### Core Components

1. **Document Management**: Handle uploaded policy documents (PDF, DOC, TXT)
2. **Policy Generator Agent**: LLM-based policy creation from documents  
3. **Rule Compiler**: Convert human-readable policies to Z3 formal logic
4. **Variable Extractor Agent**: Extract variable values from Q&A pairs
5. **Verification Engine**: Z3-based formal verification with explanations
6. **Database Layer**: Persistent storage for all components

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- PostgreSQL (if running without Docker)
- OpenAI API key or Anthropic API key

### Option 1: Docker Compose (Recommended)

1. **Clone and setup:**
```bash
git clone <repository>
cd automated_reasoning_check
```

2. **Set up environment variables:**
```bash
# Create .env file with your API keys
cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DATABASE_URL=postgresql://reasoning_user:reasoning_pass@db:5432/reasoning_db
DEBUG=false
LOG_LEVEL=INFO
EOF
```

3. **Start the system:**
```bash
docker-compose up -d
```

4. **Access the services:**
- **API Documentation**: http://localhost:9066/docs
- **Backend API**: http://localhost:9066
- **Database Admin**: http://localhost:8083 (Adminer)
- **Streamlit UI**: See "Testing UI" section below

### Option 2: Local Development

1. **Install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Set up PostgreSQL database:**
```bash
createdb reasoning_db
```

3. **Set environment variables:**
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/reasoning_db"
export OPENAI_API_KEY="your_key_here"
export DEBUG=true
```

4. **Run the application:**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🧪 Testing UI (Streamlit)

Run the Streamlit testing interface:

```bash
# Install streamlit if not already installed
pip install streamlit

# Run the UI
cd streamlit_ui
streamlit run app.py
```

The UI provides:
- System health dashboard
- Document upload interface
- Policy management
- Compilation testing
- Verification testing
- Example policies and test cases

## 📚 API Usage

### 1. Upload a Document

```bash
curl -X POST "http://localhost:9066/api/v1/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@policy_document.pdf" \
  -F "domain=hr"
```

### 2. List Generated Policies

```bash
curl "http://localhost:9066/api/v1/policies/"
```

### 3. Compile a Policy

```bash
curl -X POST "http://localhost:9066/api/v1/policies/{policy_id}/compile"
```

### 4. Verify a Q&A Pair

```bash
curl -X POST "http://localhost:9066/api/v1/policies/{policy_id}/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can I take 5 days vacation next week?",
    "answer": "Yes, but you need manager approval."
  }'
```

## 🔄 Complete Workflow Example

### 1. Upload HR Policy Document

Create a sample policy document (`hr_policy.txt`):

```text
Employee Vacation Policy

All employees are entitled to annual vacation leave. The following rules apply:

1. Vacation requests must be submitted at least 2 weeks in advance
2. Requests for more than 5 consecutive days require manager approval
3. Emergency leave does not require advance notice
4. All requests must specify the duration and dates
```

Upload it:

```bash
curl -X POST "http://localhost:9066/api/v1/documents/upload" \
  -F "file=@hr_policy.txt" \
  -F "domain=hr"
```

### 2. Check Generated Policy

Wait a moment for background processing, then list policies:

```bash
curl "http://localhost:9066/api/v1/policies/" | jq
```

### 3. Compile the Policy

Use the policy ID from step 2:

```bash
curl -X POST "http://localhost:9066/api/v1/policies/{policy_id}/compile"
```

### 4. Test Verification

Test different scenarios:

**Valid scenario:**
```bash
curl -X POST "http://localhost:9066/api/v1/policies/{policy_id}/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can I take 3 days vacation in 3 weeks?",
    "answer": "Yes, that should be fine."
  }'
```

**Invalid scenario:**
```bash
curl -X POST "http://localhost:9066/api/v1/policies/{policy_id}/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can I take vacation next week?",
    "answer": "Yes, but you only have 5 days notice."
  }'
```

## 🏗️ Project Structure

```
automated-reasoning-backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── models/
│   │   ├── database.py         # SQLAlchemy models
│   │   └── schemas.py          # Pydantic request/response models  
│   ├── services/
│   │   ├── policy_generator.py # LLM policy generation
│   │   ├── rule_compiler.py    # Z3 compilation
│   │   ├── variable_extractor.py # LLM variable extraction
│   │   ├── verification.py     # Z3 verification
│   │   └── document_processor.py # File processing
│   ├── api/
│   │   ├── documents.py        # Document upload endpoints
│   │   ├── policies.py         # Policy CRUD endpoints  
│   │   ├── compilation.py      # Compilation endpoints
│   │   ├── verification.py     # Verification endpoints
│   │   └── health.py           # Health check endpoints
│   └── core/
│       ├── config.py           # Environment configuration
│       └── database.py         # Database connection setup
├── streamlit_ui/
│   └── app.py                  # Streamlit testing interface
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## 🧠 Policy Format

The system generates policies in this structured YAML format:

```yaml
policy_name: "vacation_request_policy"
domain: "hr"
version: "1.0"
description: "Employee vacation request policy"

variables:
  - name: "advance_notice_days"
    type: "number"
    description: "Days between request submission and vacation start"
  - name: "request_type"
    type: "enum"
    possible_values: ["regular_vacation", "emergency_leave"]
    description: "Type of leave request"

rules:
  - id: "advance_notice_rule"
    condition: "request_type == 'regular_vacation' AND advance_notice_days < 14"
    conclusion: "invalid"
    description: "Regular vacation needs 2+ weeks advance notice"

constraints:
  - "advance_notice_days >= 0"
  - "vacation_duration_days > 0"

examples:
  - question: "Can I take vacation next week?"
    variables: {"advance_notice_days": 7, "request_type": "regular_vacation"}
    expected_result: "invalid"
    explanation: "Insufficient advance notice"
```

## 🔍 Verification Process

1. **Variable Extraction**: LLM extracts variables from Q&A text
2. **Z3 Constraint Checking**: Mathematical verification against formal rules
3. **Result Generation**: Explanation and suggestions for invalid scenarios
4. **Storage**: All verifications are logged for audit trails

## 📊 Monitoring

### Health Checks

- **System Health**: `GET /health`
- **Component Status**: Database, LLM services, Z3 solver, file system
- **Statistics**: `GET /status`

### Metrics

The system tracks:
- Document upload success rates
- Policy generation accuracy
- Compilation success rates
- Verification response times
- Rule violation patterns

## 🛠️ Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
python -m pytest tests/
```

### Code Quality

```bash
# Install development tools
pip install black isort mypy

# Format code
black .
isort .

# Type checking
mypy app/
```

## 🚀 Deployment

### Production Docker

```bash
# Build for production
docker build -t automated-reasoning-backend .

# Run with production settings
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e OPENAI_API_KEY="..." \
  -e DEBUG=false \
  automated-reasoning-backend
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key | Optional |
| `DEBUG` | Enable debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_FILE_SIZE` | Max upload size in bytes | `10485760` |

## 🔧 Troubleshooting

### Common Issues

1. **"No LLM service configured"**
   - Set either `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

2. **"Database connection failed"**
   - Check `DATABASE_URL` format
   - Ensure PostgreSQL is running

3. **"Z3 solver error"**
   - Verify Z3 installation: `python -c "import z3; print('Z3 OK')"`

4. **"File upload failed"**
   - Check file size limits
   - Verify upload directory permissions

### Logs

```bash
# Docker logs
docker-compose logs backend

# Application logs
tail -f logs/app.log
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
- Check the [troubleshooting section](#-troubleshooting)
- Review API documentation at `/docs`
- Use the Streamlit UI for testing
- Check system health at `/health` 