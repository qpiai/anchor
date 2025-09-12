<div align="center">
  <img src="image.png" alt="Anchor Logo" width="200"/>
  <h1>Anchor</h1>
  <p><em>AI-powered policy verification system that converts documents into formal Z3 logic for automated compliance checking.</em></p>
</div>

## Overview

This system automatically generates policies from documents, compiles them to formal Z3 constraints, and provides mathematically verified validation of user queries with mandatory variable handling.

**Key Features:**
- 📄 **Document-to-Policy**: Upload PDFs, generate policies automatically
- 🔧 **Policy Editor**: Edit variables (mandatory/optional), rules, constraints  
- ⚡ **Z3 Verification**: Formal mathematical validation
- 🧠 **Smart Variables**: LLM-based variable extraction with defaults
- 📊 **Comprehensive Testing**: All edge cases covered

## Quick Start

### Prerequisites
- Python 3.9+
- Docker and Docker Compose
- OpenAI API key

### Run with Docker
```bash
git clone <repository>
cd automated_reasoning_check

# Create .env file from template
cp .env.example .env
# Edit .env and add your OpenAI API key

# Start services
docker-compose up -d

# API: http://localhost:9066/docs
# UI: streamlit run streamlit_ui/app.py
```

### Local Development
```bash
python -m venv test_env
source test_env/bin/activate
pip install -r requirements.txt

# Start OpenAI proxy (if needed)
python openai_proxy.py

# Run application
python -m uvicorn app.main:app --host 0.0.0.0 --port 9066 --reload
```

## Usage

### 1. Upload Document
```bash
curl -X POST "http://localhost:9066/api/v1/documents/upload" \
  -F "file=@policy.pdf" -F "domain=hr"
```

### 2. Edit Policy Variables
```bash
# Make variable mandatory
curl -X PATCH "http://localhost:9066/api/v1/policies/{id}/variables/{name}" \
  -H "Content-Type: application/json" \
  -d '{"is_mandatory": true, "default_value": null}'
```

### 3. Compile Policy
```bash
curl -X POST "http://localhost:9066/api/v1/policies/{id}/compile"
```

### 4. Verify Scenarios
```bash
curl -X POST "http://localhost:9066/api/v1/policies/{id}/verify" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a full-time employee take 15 days leave?",
    "answer": "Yes"
  }'
```

## System Architecture

```
Document Upload → Policy Generation → Variable/Rule Editing → Z3 Compilation → Verification
```

### Core Components
- **Document Processor**: PDF/text parsing
- **Policy Generator**: LLM-based policy creation
- **Variable Extractor**: Smart variable extraction with mandatory/optional handling
- **Rule Compiler**: Convert rules to Z3 formal logic
- **Verification Engine**: Mathematical validation with explanations

## Project Structure

```
automated_reasoning_check/
├── app/                        # FastAPI application
│   ├── main.py                 # Application entry point
│   ├── api/                    # REST API endpoints
│   │   ├── documents.py        # Document upload & management
│   │   ├── policies.py         # Policy CRUD operations
│   │   ├── compilation.py      # Z3 compilation service
│   │   ├── verification.py     # Policy verification
│   │   ├── clarifying_questions.py
│   │   ├── policy_validation.py
│   │   └── health.py           # Health checks
│   ├── services/               # Core business logic
│   │   ├── document_processor.py
│   │   ├── policy_generator.py  # LLM policy generation
│   │   ├── variable_extractor.py # Smart variable extraction
│   │   ├── rule_compiler.py     # Z3 constraint compilation
│   │   ├── verification.py      # Mathematical verification
│   │   ├── clarifying_questions.py
│   │   └── context_manager.py
│   ├── models/                 # Data models
│   │   ├── database.py         # SQLAlchemy models
│   │   └── schemas.py          # Pydantic schemas
│   └── core/                   # Configuration
│       ├── config.py           # App configuration
│       └── database.py         # Database setup
├── streamlit_ui/               # Interactive UI
│   └── app.py                  # Streamlit interface
├── tests/                      # Test & debug scripts
│   ├── test_complete_system.py
│   ├── test_mandatory_variables.py
│   ├── test_policy_editing.py
│   ├── rule_compiler_implementation.py
│   └── debug_*.py
├── uploads/                    # Document storage
├── test_env/                   # Virtual environment
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # Container orchestration
├── Dockerfile                  # Application container
├── openai_proxy.py             # OpenAI API proxy
└── README.md
```

## Example Policies

Successfully tested with real-world policies:
- **HR Leave of Absence Policy**: Employee eligibility, duration limits, approval workflows
- **Equipment Usage Policy**: Safety requirements, authorization, time restrictions

Both demonstrate comprehensive mandatory variable handling and complex rule validation.

## Test Results

**100% Success Rate** across all edge cases:
- ✅ Valid requests with all mandatory variables → `valid`
- ✅ Missing mandatory variable detection → `needs_clarification`
- ✅ Policy violations → `invalid` with detailed explanations
- ✅ Default value usage for optional variables
- ✅ Complex rule interactions and nested conditions

## API Documentation

Interactive API documentation: `http://localhost:9066/docs`

**Key Endpoints:**
- `POST /api/v1/documents/upload` - Upload policy documents
- `GET /api/v1/policies/` - List all policies
- `PATCH /api/v1/policies/{id}/variables/{name}` - Edit variables
- `POST /api/v1/policies/{id}/compile` - Compile policy to Z3
- `POST /api/v1/policies/{id}/verify` - Verify scenarios

## Security

**⚠️ Important Security Notes:**
- **Never commit API keys or secrets** to version control
- **Use environment variables** for all sensitive configuration
- **Copy `.env.example` to `.env`** and configure your secrets there
- **Keep dependencies updated** to get security patches
- **Use strong database passwords** in production environments

See [SECURITY.md](SECURITY.md) for detailed security guidelines.

## Troubleshooting

**Common Issues:**
- Database connection → Check PostgreSQL container: `docker-compose logs postgres`
- Missing API key → Set `OPENAI_API_KEY` in `.env`
- Z3 installation → Verify: `python -c "import z3"`

**Logs:**
```bash
docker-compose logs        # All services
docker-compose logs app    # Application only
```

## Contributing

We welcome contributions! Please see [CHANGELOG.md](CHANGELOG.md) for version history.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Production Ready**: Full CRUD operations, comprehensive error handling, database persistence, and extensive test coverage.