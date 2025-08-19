from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
import yaml
import pickle
from datetime import datetime

from ..core.database import get_db
from ..models.database import Policy, PolicyCompilation, PolicyStatus, CompilationStatus
from ..models.schemas import CompilationResponse, CompilationDetailsResponse
from ..services.rule_compiler import RuleCompiler

router = APIRouter(prefix="/policies", tags=["compilation"])

# Initialize rule compiler
rule_compiler = RuleCompiler()

@router.post("/{policy_id}/compile", response_model=CompilationResponse)
async def compile_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Compile a policy to Z3 constraints"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    try:
        # Convert policy to YAML format for compilation
        policy_yaml = _convert_policy_to_yaml(policy)
        
        # Compile using rule compiler
        compiled_result = rule_compiler.compile_policy(policy_yaml)
        
        # Serialize Z3 constraints for storage
        serialized_constraints = pickle.dumps(compiled_result).decode('latin-1')
        
        # Create compilation record
        compilation = PolicyCompilation(
            policy_id=policy_id,
            z3_constraints=serialized_constraints,
            compilation_status=CompilationStatus.SUCCESS,
            compilation_errors=None
        )
        
        db.add(compilation)
        
        # Update policy status
        policy.status = PolicyStatus.COMPILED
        
        db.commit()
        db.refresh(compilation)
        
        return CompilationResponse(
            compilation_id=compilation.id,
            policy_id=policy_id,
            status=CompilationStatus.SUCCESS,
            errors=[],
            compiled_at=compilation.compiled_at
        )
        
    except Exception as e:
        # Create failed compilation record
        compilation = PolicyCompilation(
            policy_id=policy_id,
            z3_constraints=None,
            compilation_status=CompilationStatus.ERROR,
            compilation_errors=[str(e)]
        )
        
        db.add(compilation)
        db.commit()
        db.refresh(compilation)
        
        return CompilationResponse(
            compilation_id=compilation.id,
            policy_id=policy_id,
            status=CompilationStatus.ERROR,
            errors=[str(e)],
            compiled_at=compilation.compiled_at
        )

@router.get("/{policy_id}/compilation/latest", response_model=CompilationDetailsResponse)
async def get_latest_compilation(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get the latest compilation details for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Get latest compilation
    latest_compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    
    if not latest_compilation:
        raise HTTPException(status_code=404, detail="No compilation found for this policy")
    
    return latest_compilation

@router.get("/{policy_id}/compilations", response_model=list[CompilationDetailsResponse])
async def get_compilation_history(
    policy_id: uuid.UUID,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get compilation history for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    compilations = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .order_by(PolicyCompilation.compiled_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return compilations

@router.delete("/{policy_id}/compilations")
async def clear_compilation_history(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Clear all compilation history for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Delete all compilations for this policy
    deleted_count = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .delete()
    )
    
    # Reset policy status to draft
    policy.status = PolicyStatus.DRAFT
    
    db.commit()
    
    return {"message": f"Deleted {deleted_count} compilation records"}

@router.post("/{policy_id}/validate")
async def validate_policy_structure(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Validate policy structure without compiling"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    try:
        # Convert to YAML and validate structure
        policy_yaml = _convert_policy_to_yaml(policy)
        
        # Parse YAML to check structure
        policy_dict = yaml.safe_load(policy_yaml)
        
        # Basic validation
        errors = []
        
        # Required fields
        required_fields = ['policy_name', 'domain', 'variables', 'rules']
        for field in required_fields:
            if field not in policy_dict:
                errors.append(f"Missing required field: {field}")
        
        # Validate variables
        if 'variables' in policy_dict:
            for i, var in enumerate(policy_dict['variables']):
                if not isinstance(var, dict):
                    errors.append(f"Variable {i} must be a dictionary")
                    continue
                
                required_var_fields = ['name', 'type', 'description']
                for field in required_var_fields:
                    if field not in var:
                        errors.append(f"Variable {i} missing field: {field}")
        
        # Validate rules
        if 'rules' in policy_dict:
            for i, rule in enumerate(policy_dict['rules']):
                if not isinstance(rule, dict):
                    errors.append(f"Rule {i} must be a dictionary")
                    continue
                
                required_rule_fields = ['id', 'description', 'condition', 'conclusion']
                for field in required_rule_fields:
                    if field not in rule:
                        errors.append(f"Rule {i} missing field: {field}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": []  # Could add warnings for best practices
        }
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "warnings": []
        }

def _convert_policy_to_yaml(policy: Policy) -> str:
    """Convert Policy database model to YAML format for compilation"""
    
    policy_dict = {
        "policy_name": policy.name,
        "domain": policy.domain,
        "version": policy.version,
        "description": policy.description or "",
        "variables": policy.variables or [],
        "rules": policy.rules or [],
        "constraints": policy.constraints or [],
        "examples": policy.examples or []
    }
    
    return yaml.dump(policy_dict, default_flow_style=False) 