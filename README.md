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

**Option 1: Using Published Docker Image (Recommended)**
```bash
git clone <repository>
cd automated_reasoning_check

# Create .env file from template
cp .env.example .env
# Edit .env and add your OpenAI API key

# Use published Docker image - edit docker-compose.yml:
# Uncomment: image: ishantkohar/anchor-backend
# Comment: image: anchor-backend

# Fix upload permissions
chmod 777 uploads

# Start services
docker-compose up -d

# API: http://localhost:9066/docs
# UI: Create test env and run streamlit
python -m venv test_env
source test_env/bin/activate
pip install -r requirements.txt
streamlit run streamlit_ui/app.py
```

**Option 2: Build Locally**
```bash
git clone <repository>
cd automated_reasoning_check

# Create .env file from template
cp .env.example .env
# Edit .env and add your OpenAI API key

# For GPT-5 users: Edit app/core/config.py and change reasoning_effort from "low" to "high" for better results

# Build local image (ensure docker-compose.yml uses: image: anchor-backend)
docker build --network=host -t anchor-backend .

# Fix upload permissions
chmod 777 uploads

# Start services
docker-compose up -d

# API: http://localhost:9066/docs
# UI: Create test env and run streamlit
python -m venv test_env
source test_env/bin/activate
pip install streamlit
streamlit run streamlit_ui/app.py
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

Transform your policy documents into intelligent, verifiable systems. The system takes PDF documents from the `data/` folder and generates structured policies with formal validation logic.

### Input Examples
- **`data/hr_policy.pdf`**: Employee leave policies, vacation rules, approval workflows
- **`data/operations_policy.pdf`**: Equipment usage, safety protocols, authorization requirements
- **`data/legal_policy.pdf`**: Compliance rules, regulatory requirements, audit procedures

### Generated Policy Structure
Each input document becomes a structured policy containing:
- **Variables**: Mandatory/optional fields (employee_type, requested_days, etc.)
- **Rules**: Formal Z3 logic conditions (`employee_type == "full_time" AND requested_days <= 10`)
- **Validation Logic**: Automatic compliance checking with detailed explanations
- **Examples**: Test scenarios with expected outcomes

### Policy Output Example
```json
{
  "policy_name": "Employee Vacation Policy",
  "variables": [
    {
      "name": "employee_type",
      "type": "enum",
      "possible_values": ["full_time", "part_time"],
      "is_mandatory": true
    }
  ],
  "rules": [
    {
      "condition": "employee_type == 'full_time' AND requested_days <= 15",
      "conclusion": "valid",
      "description": "Full-time employees can take up to 15 days vacation"
    }
  ]
}
```

*Screenshots and detailed examples coming soon - placeholder for visual demonstrations of the policy generation process.*

## Key Features & Capabilities

**Comprehensive Policy Validation System:**
- ✅ **Complete Variable Validation**: Handles all mandatory variables → returns `valid`
- ✅ **Smart Clarification Requests**: Detects missing mandatory variables → requests `needs_clarification`
- ✅ **Detailed Violation Explanations**: Identifies policy violations → returns `invalid` with specific reasons
- ✅ **Intelligent Default Handling**: Automatically applies default values for optional variables
- ✅ **Complex Rule Processing**: Supports nested conditions and multi-variable rule interactions

## Input/Output Flow Examples

### Example 1: Valid Request
**Input Query:**
```
Question: "Can a full-time employee take 10 days vacation with 3 weeks notice?"
Answer: "Yes, the employee is full-time and provided adequate notice."
```

**System Output:**
```json
{
  "result": "valid",
  "explanation": "✅ All policy rules are satisfied. The scenario is valid according to the policy."
}
```

### Example 2: Missing Information
**Input Query:**
```
Question: "Can I take some vacation time?"
Answer: "I need time off for personal reasons."
```

**System Output:**
```json
{
  "result": "needs_clarification",
  "explanation": "❓ Missing required information for: employee_type, requested_days",
  "suggestions": ["What is your employment type (full-time/part-time)?", "How many days are you requesting?"]
}
```

### Example 3: Policy Violation
**Input Query:**
```
Question: "Can I take 20 days vacation tomorrow?"
Answer: "I need immediate time off."
```

**System Output:**
```json
{
  "result": "invalid",
  "explanation": "❌ The scenario violates the following policy rules:\n\n• advance_notice_rule: Regular vacation needs 2+ weeks advance notice\n• duration_limit_rule: Maximum 15 consecutive days allowed"
}
```

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
- Upload directory not writable → Fix permissions: `chmod 777 uploads/` or restart containers after creating uploads directory

**Logs:**
```bash
docker-compose logs        # All services
docker-compose logs app    # Application only
```

## Contributing

We welcome contributions! Please see [CHANGELOG.md](CHANGELOG.md) for version history.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
