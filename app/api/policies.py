from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
import uuid
from datetime import datetime

from ..core.database import get_db
from ..models.database import Policy, PolicyDocument, PolicyStatus
from ..models.schemas import (
    PolicyResponse, PolicyCreate, PolicyUpdate, PolicyStatusResponse,
    ErrorResponse, GenerateTestScenariosRequest, TestScenariosResponse,
    BulkTestResults, TestScenarioResult, VerificationRequest, VerificationResult
)
from pydantic import BaseModel

from ..services.test_scenario_generator import TestScenarioGeneratorService
from ..services.verification import VerificationService
from ..services.variable_extractor import VariableExtractorService
from ..models.database import PolicyCompilation, CompilationStatus

router = APIRouter(prefix="/policies", tags=["policies"])

@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get policy details by ID"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    return policy

@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: uuid.UUID,
    policy_update: PolicyUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Update only provided fields
    update_data = policy_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(policy, field, value)
    
    policy.updated_at = datetime.utcnow()
    
    # Reset status to draft if content was modified
    if any(field in update_data for field in ['variables', 'rules', 'constraints']):
        policy.status = PolicyStatus.DRAFT
    
    db.commit()
    db.refresh(policy)
    
    return policy

@router.post("/", response_model=PolicyResponse)
async def create_policy(
    policy_create: PolicyCreate,
    db: Session = Depends(get_db)
):
    """Create a new policy manually"""
    
    policy = Policy(
        name=policy_create.name,
        description=policy_create.description,
        domain=policy_create.domain,
        variables=[var.dict() for var in policy_create.variables],
        rules=[rule.dict() for rule in policy_create.rules],
        constraints=policy_create.constraints,
        examples=[ex.dict() for ex in policy_create.examples]
    )
    
    db.add(policy)
    db.commit()
    db.refresh(policy)
    
    return policy

@router.get("/by-document/{document_id}", response_model=List[PolicyResponse])
async def get_policies_by_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    """Get all policies for a specific document"""
    
    # Verify document exists
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    policies = db.query(Policy).filter(Policy.document_id == document_id).all()
    
    return policies

@router.get("/", response_model=List[PolicyResponse])
async def list_policies(
    domain: str = None,
    status: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List all policies with optional filtering"""
    
    query = db.query(Policy)
    
    if domain:
        query = query.filter(Policy.domain == domain)
    
    if status:
        query = query.filter(Policy.status == status)
    
    policies = query.offset(offset).limit(limit).all()
    
    return policies

@router.delete("/{policy_id}")
async def delete_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a policy and all associated data"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Delete associated compilations and verifications
    # (CASCADE should handle this automatically based on foreign key constraints)
    
    db.delete(policy)
    db.commit()
    
    return {"message": "Policy deleted successfully"}

@router.get("/{policy_id}/status", response_model=PolicyStatusResponse)
async def get_policy_status(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get policy status including compilation and verification info"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Get latest compilation
    latest_compilation = None
    if policy.compilations:
        latest_compilation = max(policy.compilations, key=lambda c: c.compiled_at)
    
    # Get latest verification
    latest_verification = None
    if policy.verifications:
        latest_verification = max(policy.verifications, key=lambda v: v.verified_at)
    
    return PolicyStatusResponse(
        policy_status=policy.status,
        compilation_status=latest_compilation.compilation_status if latest_compilation else None,
        last_verified=latest_verification.verified_at if latest_verification else None
    )

@router.post("/{policy_id}/clone", response_model=PolicyResponse)
async def clone_policy(
    policy_id: uuid.UUID,
    new_name: str = None,
    db: Session = Depends(get_db)
):
    """Clone an existing policy with optional new name"""
    
    original_policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not original_policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Create new policy with cloned data
    cloned_policy = Policy(
        name=new_name or f"{original_policy.name} (Copy)",
        description=original_policy.description,
        domain=original_policy.domain,
        version="1.0",  # Reset version for clone
        variables=original_policy.variables,
        rules=original_policy.rules,
        constraints=original_policy.constraints,
        examples=original_policy.examples
    )
    
    db.add(cloned_policy)
    db.commit()
    db.refresh(cloned_policy)
    
    return cloned_policy

class VariableUpdateRequest(BaseModel):
    is_mandatory: bool = None
    default_value: str = None

@router.patch("/{policy_id}/variables/{variable_name}")
async def update_policy_variable(
    policy_id: uuid.UUID,
    variable_name: str,
    request: VariableUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update specific properties of a policy variable"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if not policy.variables:
        raise HTTPException(status_code=400, detail="Policy has no variables")
    
    # Find the variable to update
    variables = policy.variables.copy()
    variable_found = False
    
    for i, var in enumerate(variables):
        if var['name'] == variable_name:
            variable_found = True
            # Update only provided fields
            if request.is_mandatory is not None:
                variables[i]['is_mandatory'] = request.is_mandatory
            if request.default_value is not None:
                if request.default_value == "":  # Empty string means remove default
                    variables[i].pop('default_value', None)
                else:
                    variables[i]['default_value'] = request.default_value
            break
    
    if not variable_found:
        raise HTTPException(status_code=404, detail=f"Variable '{variable_name}' not found")
    
    # Update the policy
    policy.variables = variables
    policy.updated_at = datetime.utcnow()
    # Reset status to draft since variables changed
    policy.status = PolicyStatus.DRAFT
    
    # Flag the JSON field as modified so SQLAlchemy detects the change
    flag_modified(policy, 'variables')
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Variable '{variable_name}' updated successfully", "policy": policy}

# Additional request models for CRUD operations
class VariableCreateRequest(BaseModel):
    name: str
    type: str  # string, number, boolean, enum, date
    description: str
    possible_values: List[str] = None
    is_mandatory: bool = True
    default_value: str = None

class RuleCreateRequest(BaseModel):
    id: str
    description: str
    condition: str
    conclusion: str  # valid, invalid
    priority: int = 1

class RuleUpdateRequest(BaseModel):
    description: str = None
    condition: str = None
    conclusion: str = None
    priority: int = None

# Variable CRUD endpoints
@router.post("/{policy_id}/variables")
async def add_policy_variable(
    policy_id: uuid.UUID,
    request: VariableCreateRequest,
    db: Session = Depends(get_db)
):
    """Add a new variable to the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    variables = policy.variables.copy() if policy.variables else []
    
    # Check if variable name already exists
    if any(var['name'] == request.name for var in variables):
        raise HTTPException(status_code=400, detail=f"Variable '{request.name}' already exists")
    
    # Create new variable
    new_variable = {
        "name": request.name,
        "type": request.type,
        "description": request.description,
        "is_mandatory": request.is_mandatory
    }
    
    if request.possible_values:
        new_variable["possible_values"] = request.possible_values
    
    if request.default_value:
        new_variable["default_value"] = request.default_value
    
    variables.append(new_variable)
    
    # Update policy
    policy.variables = variables
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Variable '{request.name}' added successfully", "policy": policy}

@router.delete("/{policy_id}/variables/{variable_name}")
async def delete_policy_variable(
    policy_id: uuid.UUID,
    variable_name: str,
    db: Session = Depends(get_db)
):
    """Delete a variable from the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if not policy.variables:
        raise HTTPException(status_code=400, detail="Policy has no variables")
    
    # Remove the variable
    variables = [var for var in policy.variables if var['name'] != variable_name]
    
    if len(variables) == len(policy.variables):
        raise HTTPException(status_code=404, detail=f"Variable '{variable_name}' not found")
    
    # Update policy
    policy.variables = variables
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Variable '{variable_name}' deleted successfully", "policy": policy}

# Rule CRUD endpoints
@router.post("/{policy_id}/rules")
async def add_policy_rule(
    policy_id: uuid.UUID,
    request: RuleCreateRequest,
    db: Session = Depends(get_db)
):
    """Add a new rule to the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    rules = policy.rules.copy() if policy.rules else []
    
    # Check if rule ID already exists
    if any(rule['id'] == request.id for rule in rules):
        raise HTTPException(status_code=400, detail=f"Rule '{request.id}' already exists")
    
    # Create new rule
    new_rule = {
        "id": request.id,
        "description": request.description,
        "condition": request.condition,
        "conclusion": request.conclusion,
        "priority": request.priority
    }
    
    rules.append(new_rule)
    
    # Update policy
    policy.rules = rules
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    # Flag the JSON field as modified so SQLAlchemy detects the change
    flag_modified(policy, 'rules')
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Rule '{request.id}' added successfully", "policy": policy}

@router.patch("/{policy_id}/rules/{rule_id}")
async def update_policy_rule(
    policy_id: uuid.UUID,
    rule_id: str,
    request: RuleUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a specific rule in the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if not policy.rules:
        raise HTTPException(status_code=400, detail="Policy has no rules")
    
    # Find and update the rule
    rules = policy.rules.copy()
    rule_found = False
    
    for i, rule in enumerate(rules):
        if rule['id'] == rule_id:
            rule_found = True
            # Update only provided fields
            if request.description is not None:
                rules[i]['description'] = request.description
            if request.condition is not None:
                rules[i]['condition'] = request.condition
            if request.conclusion is not None:
                rules[i]['conclusion'] = request.conclusion
            if request.priority is not None:
                rules[i]['priority'] = request.priority
            break
    
    if not rule_found:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    
    # Update policy
    policy.rules = rules
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    # Flag the JSON field as modified so SQLAlchemy detects the change
    flag_modified(policy, 'rules')
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Rule '{rule_id}' updated successfully", "policy": policy}

@router.delete("/{policy_id}/rules/{rule_id}")
async def delete_policy_rule(
    policy_id: uuid.UUID,
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Delete a rule from the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if not policy.rules:
        raise HTTPException(status_code=400, detail="Policy has no rules")
    
    # Remove the rule
    rules = [rule for rule in policy.rules if rule['id'] != rule_id]
    
    if len(rules) == len(policy.rules):
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    
    # Update policy
    policy.rules = rules
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    # Flag the JSON field as modified so SQLAlchemy detects the change
    flag_modified(policy, 'rules')
    
    db.commit()
    db.refresh(policy)
    
    return {"message": f"Rule '{rule_id}' deleted successfully", "policy": policy}

# Constraints CRUD endpoints
@router.post("/{policy_id}/constraints")
async def add_policy_constraint(
    policy_id: uuid.UUID,
    constraint: str,
    db: Session = Depends(get_db)
):
    """Add a new constraint to the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    constraints = policy.constraints.copy() if policy.constraints else []
    
    # Check if constraint already exists
    if constraint in constraints:
        raise HTTPException(status_code=400, detail="Constraint already exists")
    
    constraints.append(constraint)
    
    # Update policy
    policy.constraints = constraints
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    db.commit()
    db.refresh(policy)
    
    return {"message": "Constraint added successfully", "policy": policy}

@router.delete("/{policy_id}/constraints")
async def delete_policy_constraint(
    policy_id: uuid.UUID,
    constraint: str,
    db: Session = Depends(get_db)
):
    """Delete a constraint from the policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if not policy.constraints:
        raise HTTPException(status_code=400, detail="Policy has no constraints")
    
    # Remove the constraint
    constraints = [c for c in policy.constraints if c != constraint]
    
    if len(constraints) == len(policy.constraints):
        raise HTTPException(status_code=404, detail="Constraint not found")
    
    # Update policy
    policy.constraints = constraints
    policy.updated_at = datetime.utcnow()
    policy.status = PolicyStatus.DRAFT
    
    db.commit()
    db.refresh(policy)
    
    return {"message": "Constraint deleted successfully", "policy": policy}

# Test Scenario Generation endpoints
@router.post("/{policy_id}/generate-test-scenarios", response_model=TestScenariosResponse)
async def generate_test_scenarios(
    policy_id: uuid.UUID,
    request: GenerateTestScenariosRequest = GenerateTestScenariosRequest(),
    db: Session = Depends(get_db)
):
    """Generate comprehensive test scenarios for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if policy.status != PolicyStatus.COMPILED:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before generating test scenarios"
        )
    
    # Convert policy to dict format for the service
    policy_dict = {
        "name": policy.name,
        "domain": policy.domain,
        "version": policy.version,
        "description": policy.description,
        "variables": policy.variables or [],
        "rules": policy.rules or [],
        "constraints": policy.constraints or []
    }
    
    # Initialize service and generate scenarios
    generator = TestScenarioGeneratorService()
    scenarios_response = await generator.generate_test_scenarios(policy_dict, request)
    
    return scenarios_response

@router.post("/{policy_id}/test-scenarios", response_model=BulkTestResults)
async def run_test_scenarios(
    policy_id: uuid.UUID,
    request: GenerateTestScenariosRequest = GenerateTestScenariosRequest(),
    db: Session = Depends(get_db)
):
    """Generate test scenarios and run them against the verification system"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    if policy.status != PolicyStatus.COMPILED:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before testing"
        )
    
    # Generate scenarios first
    policy_dict = {
        "name": policy.name,
        "domain": policy.domain,
        "version": policy.version,
        "description": policy.description,
        "variables": policy.variables or [],
        "rules": policy.rules or [],
        "constraints": policy.constraints or []
    }
    
    generator = TestScenarioGeneratorService()
    scenarios_response = await generator.generate_test_scenarios(policy_dict, request)
    
    # Get the latest compilation for this policy
    latest_compilation = db.query(PolicyCompilation).filter(
        PolicyCompilation.policy_id == policy_id,
        PolicyCompilation.compilation_status == CompilationStatus.SUCCESS
    ).order_by(PolicyCompilation.compiled_at.desc()).first()
    
    if not latest_compilation:
        raise HTTPException(status_code=400, detail="No successful compilation found for policy")
    
    # Initialize services  
    verification_service = VerificationService()
    variable_extractor = VariableExtractorService()
    results = []
    passed_count = 0
    
    for scenario in scenarios_response.scenarios:
        try:
            # Extract variables from Q&A pair (following verification.py pattern)
            extracted_variables = await variable_extractor.extract_variables(
                scenario.question,
                scenario.answer, 
                policy.variables or []
            )
            
            # Run Z3 verification
            verification_result = verification_service.verify_scenario(
                extracted_variables,
                latest_compilation.z3_constraints,
                policy.rules or []
            )
            
            # Map result to enum
            if verification_result['result'] == 'valid':
                actual_result = VerificationResult.VALID
            elif verification_result['result'] == 'invalid':
                actual_result = VerificationResult.INVALID
            elif verification_result['result'] == 'needs_clarification':
                actual_result = VerificationResult.NEEDS_CLARIFICATION
            else:
                actual_result = VerificationResult.ERROR
            
            # Check if result matches expectation
            passed = actual_result == scenario.expected_result
            if passed:
                passed_count += 1
            
            # Create result record
            result = TestScenarioResult(
                scenario_id=scenario.id,
                actual_result=actual_result,
                passed=passed,
                explanation=verification_result['explanation'],
                error_message=None
            )
            
            results.append(result)
            
        except Exception as e:
            # Handle verification errors
            result = TestScenarioResult(
                scenario_id=scenario.id,
                actual_result=VerificationResult.ERROR,
                passed=False,
                explanation=None,
                error_message=str(e)
            )
            results.append(result)
    
    # Calculate success rate
    total_scenarios = len(scenarios_response.scenarios)
    success_rate = passed_count / total_scenarios if total_scenarios > 0 else 0.0
    
    return BulkTestResults(
        policy_id=policy_id,
        total_scenarios=total_scenarios,
        passed_scenarios=passed_count,
        failed_scenarios=total_scenarios - passed_count,
        success_rate=success_rate,
        results=results,
        tested_at=datetime.now()
    ) 