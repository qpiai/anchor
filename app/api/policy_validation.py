from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Set
import uuid
import re

from ..core.database import get_db
from ..models.database import Policy

router = APIRouter(prefix="/policies", tags=["policy_validation"])

@router.get("/{policy_id}/validate")
async def validate_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Validate policy for consistency and completeness"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    validation_result = analyze_policy_consistency(policy)
    
    return {
        "policy_id": policy_id,
        "valid": len(validation_result["errors"]) == 0,
        "warnings": validation_result["warnings"],
        "errors": validation_result["errors"],
        "suggestions": validation_result["suggestions"]
    }

@router.post("/{policy_id}/fix-missing-variables")
async def fix_missing_variables(
    policy_id: uuid.UUID, 
    auto_add: bool = True,
    db: Session = Depends(get_db)
):
    """Automatically fix missing variables referenced in rules"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Find missing variables
    defined_vars = {var['name'] for var in policy.variables or []}
    referenced_vars = extract_variables_from_rules(policy.rules or [])
    missing_vars = referenced_vars - defined_vars
    
    if not missing_vars:
        return {
            "message": "No missing variables found",
            "missing_variables": []
        }
    
    if auto_add:
        # Add missing variables to the policy
        new_variables = []
        for var_name in missing_vars:
            var_type, description = infer_variable_type_and_description(var_name)
            new_variables.append({
                "name": var_name,
                "type": var_type,
                "description": description,
                "possible_values": ["true", "false"] if var_type == "boolean" else []
            })
        
        # Update policy
        updated_variables = (policy.variables or []) + new_variables
        policy.variables = updated_variables
        db.commit()
        
        return {
            "message": f"Added {len(new_variables)} missing variables",
            "added_variables": new_variables,
            "missing_variables": list(missing_vars)
        }
    else:
        return {
            "message": f"Found {len(missing_vars)} missing variables",
            "missing_variables": list(missing_vars)
        }

def analyze_policy_consistency(policy: Policy) -> Dict[str, List[str]]:
    """Analyze policy for consistency issues"""
    
    warnings = []
    errors = []
    suggestions = []
    
    # Check variable consistency
    defined_vars = {var['name'] for var in policy.variables or []}
    referenced_vars = extract_variables_from_rules(policy.rules or [])
    missing_vars = referenced_vars - defined_vars
    unused_vars = defined_vars - referenced_vars
    
    if missing_vars:
        errors.append(f"Rules reference undefined variables: {', '.join(missing_vars)}")
        suggestions.append("Use the /fix-missing-variables endpoint to automatically add missing variables")
    
    if unused_vars:
        warnings.append(f"Defined variables not used in any rules: {', '.join(unused_vars)}")
    
    # Check rule logic consistency
    if policy.rules:
        # Check for contradictory rules
        valid_rules = [r for r in policy.rules if r.get('conclusion') == 'valid']
        invalid_rules = [r for r in policy.rules if r.get('conclusion') == 'invalid']
        
        if not valid_rules:
            warnings.append("No rules with 'valid' conclusion found - scenarios may never be valid")
        
        if not invalid_rules:
            warnings.append("No rules with 'invalid' conclusion found - no explicit violations defined")
    
    # Check constraint syntax
    for constraint in policy.constraints or []:
        if not is_valid_constraint_syntax(constraint):
            errors.append(f"Invalid constraint syntax: {constraint}")
    
    return {
        "warnings": warnings,
        "errors": errors, 
        "suggestions": suggestions
    }

def extract_variables_from_rules(rules: List[Dict]) -> Set[str]:
    """Extract all variable names referenced in rules"""
    variables = set()
    
    for rule in rules:
        condition = rule.get('condition', '')
        # Use regex to find variable names (alphanumeric + underscore, not starting with digit)
        var_matches = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', condition)
        
        # Filter out logical operators and common values
        excluded = {'AND', 'OR', 'NOT', 'and', 'or', 'not', 'true', 'false', 'TRUE', 'FALSE'}
        
        for match in var_matches:
            # Skip if it looks like a string value (in quotes) or number
            if match not in excluded and not match.isdigit():
                variables.add(match)
    
    return variables

def infer_variable_type_and_description(var_name: str) -> tuple[str, str]:
    """Infer variable type and generate description from variable name"""
    
    var_lower = var_name.lower()
    
    # Boolean patterns
    if (var_name.startswith('is_') or var_name.startswith('has_') or 
        var_name.startswith('can_') or var_name.startswith('should_') or
        '_approved' in var_lower or '_required' in var_lower or
        '_checked' in var_lower or '_logged' in var_lower):
        return "boolean", f"Indicates whether {var_name.replace('_', ' ')}"
    
    # Number patterns
    if ('_count' in var_lower or '_duration' in var_lower or '_hours' in var_lower or
        '_days' in var_lower or '_amount' in var_lower or '_cost' in var_lower or
        '_number' in var_lower or '_quantity' in var_lower):
        return "number", f"Numeric value for {var_name.replace('_', ' ')}"
    
    # Enum patterns (type, status, category, level, etc.)
    if ('_type' in var_lower or '_status' in var_lower or '_category' in var_lower or
        '_level' in var_lower or '_role' in var_lower or '_grade' in var_lower):
        return "enum", f"Category or type for {var_name.replace('_', ' ')}"
    
    # Default to string
    return "string", f"Text value for {var_name.replace('_', ' ')}"

def is_valid_constraint_syntax(constraint: str) -> bool:
    """Check if constraint has valid syntax"""
    try:
        # Basic syntax validation - contains variable names and operators
        operators = ['>', '<', '>=', '<=', '==', '!=', '+', '-', '*', '/']
        has_operator = any(op in constraint for op in operators)
        has_variable = bool(re.search(r'[a-zA-Z_][a-zA-Z0-9_]*', constraint))
        return has_operator and has_variable
    except:
        return False

@router.get("/{policy_id}/variable-analysis") 
async def analyze_variables(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Analyze variable usage and provide insights"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    defined_vars = {var['name']: var for var in policy.variables or []}
    referenced_vars = extract_variables_from_rules(policy.rules or [])
    
    analysis = {
        "total_defined_variables": len(defined_vars),
        "total_referenced_variables": len(referenced_vars),
        "defined_variables": list(defined_vars.keys()),
        "referenced_variables": list(referenced_vars),
        "missing_variables": list(referenced_vars - set(defined_vars.keys())),
        "unused_variables": list(set(defined_vars.keys()) - referenced_vars),
        "variable_details": []
    }
    
    # Add details for each referenced variable
    for var_name in referenced_vars:
        if var_name in defined_vars:
            var_info = defined_vars[var_name]
            analysis["variable_details"].append({
                "name": var_name,
                "status": "defined",
                "type": var_info["type"],
                "description": var_info["description"],
                "possible_values": var_info.get("possible_values", [])
            })
        else:
            inferred_type, inferred_desc = infer_variable_type_and_description(var_name)
            analysis["variable_details"].append({
                "name": var_name,
                "status": "missing",
                "inferred_type": inferred_type,
                "inferred_description": inferred_desc
            })
    
    return analysis