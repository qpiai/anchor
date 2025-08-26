from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from enum import Enum

class PolicyStatus(str, Enum):
    DRAFT = "draft"
    COMPILED = "compiled"
    ACTIVE = "active"

class CompilationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"

class VerificationResult(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    ERROR = "ERROR"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

# Document schemas
class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: str

class PolicyDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content: str
    domain: str
    uploaded_at: datetime

    class Config:
        from_attributes = True

# Policy schemas
class PolicyVariable(BaseModel):
    name: str
    type: str  # string, number, boolean, date, enum
    description: str
    possible_values: Optional[List[str]] = None
    is_mandatory: bool = True
    default_value: Optional[str] = None

class PolicyRule(BaseModel):
    id: str
    description: str
    condition: str
    conclusion: str
    priority: int = 1

class PolicyExample(BaseModel):
    question: str
    variables: Dict[str, Any]
    expected_result: str
    explanation: str

class PolicyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    domain: str
    variables: List[PolicyVariable]
    rules: List[PolicyRule]
    constraints: List[str] = []
    examples: List[PolicyExample] = []

class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    variables: Optional[List[PolicyVariable]] = None
    rules: Optional[List[PolicyRule]] = None
    constraints: Optional[List[str]] = None
    examples: Optional[List[PolicyExample]] = None

class PolicyResponse(BaseModel):
    id: uuid.UUID
    document_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    domain: str
    version: str
    status: PolicyStatus
    variables: Optional[List[Dict[str, Any]]]
    rules: Optional[List[Dict[str, Any]]]
    constraints: Optional[List[str]]
    examples: Optional[List[Dict[str, Any]]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Compilation schemas
class CompilationResponse(BaseModel):
    compilation_id: uuid.UUID
    policy_id: uuid.UUID
    status: CompilationStatus
    errors: List[str] = []
    compiled_at: datetime

class CompilationDetailsResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    z3_constraints: Optional[str]
    compilation_status: CompilationStatus
    compilation_errors: Optional[List[str]]
    compiled_at: datetime

    class Config:
        from_attributes = True

# Verification schemas
class VerificationRequest(BaseModel):
    question: str
    answer: str

class VerificationResponse(BaseModel):
    verification_id: uuid.UUID
    result: VerificationResult
    extracted_variables: Dict[str, Any]
    explanation: str
    suggestions: List[str] = []

class VerificationHistoryResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    question: str
    answer: str
    extracted_variables: Optional[Dict[str, Any]]
    verification_result: VerificationResult
    explanation: Optional[str]
    suggestions: Optional[List[str]]
    verified_at: datetime

    class Config:
        from_attributes = True

# Health and status schemas
class HealthResponse(BaseModel):
    status: str
    components: Dict[str, str]

class PolicyStatusResponse(BaseModel):
    policy_status: PolicyStatus
    compilation_status: Optional[CompilationStatus]
    last_verified: Optional[datetime]

# Error schemas
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

# Test Scenario schemas
class TestScenarioCategory(str, Enum):
    MISSING_MANDATORY = "missing_mandatory"
    VALID_SCENARIOS = "valid_scenarios"
    RULE_VIOLATIONS = "rule_violations"
    EDGE_CASES = "edge_cases"

class TestScenario(BaseModel):
    id: str
    category: TestScenarioCategory
    name: str
    question: str
    answer: str
    expected_result: VerificationResult
    expected_missing_variables: Optional[List[str]] = None
    expected_violated_rule: Optional[str] = None
    expected_variables: Optional[Dict[str, Any]] = None
    description: str

class TestScenarioMetadata(BaseModel):
    total_scenarios: int
    categories: Dict[TestScenarioCategory, int]
    generation_time: datetime
    policy_version: str

class TestScenariosResponse(BaseModel):
    scenarios: List[TestScenario]
    metadata: TestScenarioMetadata

class GenerateTestScenariosRequest(BaseModel):
    max_scenarios_per_category: int = 5
    include_categories: List[TestScenarioCategory] = [
        TestScenarioCategory.MISSING_MANDATORY,
        TestScenarioCategory.VALID_SCENARIOS,
        TestScenarioCategory.RULE_VIOLATIONS,
        TestScenarioCategory.EDGE_CASES
    ]

class TestScenarioResult(BaseModel):
    scenario_id: str
    actual_result: VerificationResult
    passed: bool
    actual_missing_variables: Optional[List[str]] = None
    actual_violated_rule: Optional[str] = None
    explanation: Optional[str] = None
    error_message: Optional[str] = None

class BulkTestResults(BaseModel):
    policy_id: uuid.UUID
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    success_rate: float
    results: List[TestScenarioResult]
    tested_at: datetime 