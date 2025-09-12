# Product Requirements Document: Anchor

## 1. Project Overview

**Product Name:** Anchor Service  
**Version:** 1.0  
**Type:** REST API Backend Service  
**Purpose:** Multi-agent AI system for autonomous policy generation and verification

### Core Innovation
Build a backend service that implements AWS Bedrock Guardrails-style policy verification but with autonomous policy generation capabilities. The system uses multiple LLM agents to generate domain-specific policies from documents, compiles them to Z3 constraints, and provides verified validation of user queries.

## 2. System Architecture

### High-Level Flow
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

## 3. Technical Requirements

### Technology Stack
- **Framework**: FastAPI (Python 3.9+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Formal Logic**: Z3 Solver (Microsoft Z3Py)
- **LLM Integration**: OpenAI GPT-4 or Anthropic Claude
- **File Processing**: PyPDF2, python-docx for document parsing
- **Deployment**: Docker containers
- **Authentication**: JWT-based (optional for v1)

### Dependencies
```txt
fastapi==0.104.1
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
z3-solver==4.12.2.0
pydantic==2.5.0
python-multipart==0.0.6
PyYAML==6.0.1
openai==1.3.0
anthropic==0.7.0
PyPDF2==3.0.1
python-docx==1.1.0
uvicorn==0.24.0
```

## 4. Database Schema

### Tables Required

**policy_documents**
- id (UUID, Primary Key)
- filename (String)
- content (Text)
- domain (String) - hr, legal, finance, etc.
- uploaded_at (DateTime)

**policies** 
- id (UUID, Primary Key)
- document_id (UUID, Foreign Key)
- name (String)
- description (Text)
- domain (String)
- version (String)
- status (Enum: draft, compiled, active)
- variables (JSON) - Policy variables with types
- rules (JSON) - Policy rules and conditions
- constraints (JSON) - Global constraints
- examples (JSON) - Test scenarios
- created_at/updated_at (DateTime)

**policy_compilations**
- id (UUID, Primary Key)
- policy_id (UUID, Foreign Key)
- z3_constraints (Text) - Serialized Z3 constraints
- compilation_status (String) - success, error
- compilation_errors (JSON)
- compiled_at (DateTime)

**verifications**
- id (UUID, Primary Key)
- policy_id (UUID, Foreign Key)
- question (Text)
- answer (Text)
- extracted_variables (JSON)
- verification_result (String) - valid, invalid, error
- explanation (Text)
- suggestions (JSON)
- verified_at (DateTime)

## 5. API Endpoints Specification

### Document Management
```http
POST /documents/upload
Content-Type: multipart/form-data
Body: file, domain
Response: {document_id, filename, status}
```

### Policy Management  
```http
GET /policies/{policy_id}
Response: PolicyResponse (complete policy details)

PUT /policies/{policy_id}
Body: PolicyUpdate (variables, rules, constraints)
Response: Updated PolicyResponse

GET /policies/by-document/{document_id}
Response: List of policies for document
```

### Compilation
```http
POST /policies/{policy_id}/compile
Response: {compilation_id, status, errors[], compiled_at}

GET /policies/{policy_id}/compilation/latest
Response: Latest compilation details
```

### Verification
```http
POST /policies/{policy_id}/verify
Body: {question: string, answer: string}
Response: {verification_id, result, extracted_variables, explanation, suggestions[]}

GET /policies/{policy_id}/verifications
Query: ?limit=50&offset=0
Response: Paginated verification history
```

### Health & Status
```http
GET /health
Response: {status: "healthy", components: {...}}

GET /policies/{policy_id}/status
Response: {policy_status, compilation_status, last_verified}
```

## 6. Service Implementation Details

### 6.1 Policy Generator Service

**File**: `app/services/policy_generator.py`

**Purpose**: Convert uploaded documents into structured policies using LLM

**Key Functions**:
```python
async def generate_policy_from_document(document_content: str, domain: str) -> Dict[str, Any]
async def enhance_policy_with_examples(policy: Dict) -> Dict
async def validate_generated_policy(policy: Dict) -> List[str]  # Return validation errors
```

**LLM System Prompt**: Use the provided "Policy Generator Agent System Prompt" that creates YAML policies with variables, rules, and constraints.
  

**Output Format**: Structured policy in the exact format required by the Rule Compiler.

### 6.2 Rule Compiler Service

**File**: `app/services/rule_compiler.py`

**Purpose**: Convert YAML policies to Z3 formal logic constraints

**Implementation**: Use the complete `RuleCompiler` class code provided earlier with these key methods:

```python
class RuleCompiler:
    def compile_policy(self, policy_yaml: str) -> Dict[str, Any]
    def _create_z3_variables(self, variables: List[Dict])
    def _compile_rule(self, rule: Dict) -> Any
    def _parse_condition(self, condition: str) -> Any
    def _parse_atomic_condition(self, condition: str) -> Any
    def _get_z3_expression(self, expr: str) -> Any
```

**Critical**: Include the complete implementation provided in our earlier conversation, including support for:
- Variable types: string, number, boolean, enum, date
- Logical operators: AND, OR, NOT
- Comparison operators: ==, !=, <, >, <=, >=
- Z3 constraint generation and validation

### 6.3 Variable Extractor Service  

**File**: `app/services/variable_extractor.py`

**Purpose**: Extract variable values from natural language Q&A pairs

**Key Functions**:
```python
async def extract_variables(question: str, answer: str, policy_variables: List[Dict]) -> Dict[str, Any]
async def validate_extracted_variables(variables: Dict, policy_variables: List[Dict]) -> List[str]
```

**LLM Integration**: Create system prompt that takes policy variable definitions and extracts values from Q&A text.

**System Prompt Pattern**:
```
You are a Variable Extractor Agent. Given policy variables and a Q&A pair, extract the variable values.

Variables:
- name: "advance_notice_days", type: "number", description: "Days between request and vacation start"
- name: "request_type", type: "enum", values: ["vacation", "sick"], description: "Type of leave"

Q&A:
Question: "Can I take vacation next week?"
Answer: "Yes, you can take 3 days vacation."

Extract: {advance_notice_days: 7, vacation_duration_days: 3, request_type: "vacation"}
```

### 6.4 Verification Service

**File**: `app/services/verification.py` 

**Purpose**: Use Z3 to verify extracted variables against compiled policies

**Key Functions**:
```python
def verify_scenario(extracted_variables: Dict, z3_constraints: str, policy_rules: List[Dict]) -> Dict[str, Any]
def explain_verification_result(result: bool, failed_rules: List[str]) -> str
def generate_suggestions(failed_rules: List[Dict], extracted_variables: Dict) -> List[str]
```

**Implementation Logic**:
1. Load serialized Z3 constraints
2. Create Z3 solver instance  
3. Add variable assignments from extracted_variables
4. Check satisfiability against each rule
5. Generate explanations for failures
6. Provide suggestions for making invalid scenarios valid

## 7. Integration Points for Langflow

### Background Task Processing
Implement background tasks for long-running operations:

```python
from fastapi import BackgroundTasks

@app.post("/documents/upload")
async def upload_document(background_tasks: BackgroundTasks):
    # Save document immediately
    # Trigger background policy generation
    background_tasks.add_task(generate_policy_background, document_id, content, domain)
```

### Webhook Support (Optional)
```http
POST /webhooks/policy-generated/{document_id}
POST /webhooks/compilation-complete/{policy_id}
```

### Streaming Responses (Optional)
```http
GET /policies/{policy_id}/generate/stream
Content-Type: text/event-stream
```

## 8. Key Implementation Files

### Project Structure
```
automated-reasoning-backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── models/
│   │   ├── database.py         # SQLAlchemy models (all tables above)
│   │   └── schemas.py          # Pydantic request/response models  
│   ├── services/
│   │   ├── policy_generator.py # LLM policy generation
│   │   ├── rule_compiler.py    # Z3 compilation (use provided code)
│   │   ├── variable_extractor.py # LLM variable extraction
│   │   └── verification.py     # Z3 verification
│   ├── api/
│   │   ├── documents.py        # Document upload endpoints
│   │   ├── policies.py         # Policy CRUD endpoints  
│   │   ├── compilation.py      # Compilation endpoints
│   │   └── verification.py     # Verification endpoints
│   └── core/
│       ├── config.py           # Environment configuration
│       └── database.py         # Database connection setup
├── requirements.txt
├── docker-compose.yml
└── README.md
```

## 9. Critical Code References

### 9.1 Complete Rule Compiler Implementation
The Z3 rule compiler code provided earlier must be implemented exactly as specified, including:

- `RuleCompiler` class with all methods
- Support for all variable types (string, number, boolean, enum, date)
- Logical operator parsing (AND, OR, NOT)
- Comparison operator handling
- Z3 constraint generation
- Error handling and validation

### 9.2 Policy Generator System Prompt
Use the complete "Policy Generator Agent System Prompt" provided earlier that outputs structured YAML policies.

### 9.3 Database Models
Implement all SQLAlchemy models as specified in the database schema section.

## 10. Testing Requirements

### Unit Tests Required
- Rule compiler with various policy formats
- Variable extractor with different Q&A patterns  
- Z3 verification with valid/invalid scenarios
- Policy generator with sample documents

### Integration Tests Required
- Complete flow: Document → Policy → Compilation → Verification
- Error handling for malformed inputs
- Performance tests with large policies

### Test Data
- Sample HR policy documents
- Example policies with variables, rules, constraints
- Q&A test scenarios with expected results

## 11. Performance Requirements

- **Document Upload**: < 2 seconds response time
- **Policy Generation**: < 30 seconds for typical documents
- **Rule Compilation**: < 5 seconds for policies with 50+ rules
- **Verification**: < 1 second for individual Q&A pairs
- **Concurrent Users**: Support 10+ simultaneous verification requests

## 12. Error Handling

### Error Response Format
```json
{
  "error": {
    "code": "COMPILATION_FAILED",
    "message": "Rule syntax error in rule_001",
    "details": {
      "rule_id": "rule_001", 
      "line": "advance_notice_days << 14",
      "suggestion": "Use < instead of <<"
    }
  }
}
```

### Error Categories
- Document parsing errors
- Policy generation failures  
- Rule compilation errors
- Variable extraction issues
- Z3 verification failures
- Database connection errors

## 13. Security Considerations

- Input validation for all file uploads
- SQL injection prevention (use SQLAlchemy ORM)
- Rate limiting on API endpoints
- File size limits (max 10MB documents)
- Sanitize generated Z3 code before execution

## 14. Deployment Instructions

### Docker Setup
```yaml
# docker-compose.yml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "9066:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/reasoning
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - db
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=reasoning
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Environment Variables
```
DATABASE_URL=postgresql://user:pass@localhost:5432/reasoning
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key  
LOG_LEVEL=INFO
DEBUG=False
```

## 15. Success Criteria

### Functional Requirements Met
- [x] Document upload and processing
- [x] Autonomous policy generation from documents
- [x] Manual policy editing capabilities
- [x] Z3 compilation of policies to formal logic
- [x] Variable extraction from Q&A pairs
- [x] Formal verification with explanations
- [x] Complete API for Langflow integration

### Quality Requirements Met
- Rule compilation accuracy: 95%+ for well-formed policies
- Variable extraction accuracy: 90%+ for clear Q&A pairs
- Verification response time: < 1 second average
- System uptime: 99%+ availability

## 16. Future Enhancements

- Multi-domain policy libraries
- Policy version control and change tracking
- Advanced verification reporting and analytics
- Integration with external compliance databases
- Real-time collaboration on policy editing
- Machine learning improvements to variable extraction accuracy

---

## Implementation Notes for Cursor

1. **Start with database models and basic FastAPI setup**
2. **Implement Rule Compiler service first** (using provided complete code)
3. **Add Policy Generator with LLM integration**  
4. **Build Variable Extractor service**
5. **Complete Verification Engine**
6. **Add all API endpoints**
7. **Implement error handling and validation**
8. **Add comprehensive testing**

The rule compiler code and policy generator prompts provided in this conversation contain the core logic and should be implemented exactly as specified for the mathematical verification to work correctly.



## Also Create a simple streamlit ui for testing