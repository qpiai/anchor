from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
import pickle

from ..core.database import get_db
from ..models.database import Policy, PolicyCompilation, Verification, VerificationResult, CompilationStatus
from ..models.schemas import (
    VerificationRequest, VerificationResponse, VerificationHistoryResponse
)
from ..services.variable_extractor import VariableExtractorService
from ..services.verification import VerificationService

router = APIRouter(prefix="/policies", tags=["verification"])

# Initialize services
variable_extractor = VariableExtractorService()
verification_service = VerificationService()

@router.post("/{policy_id}/verify", response_model=VerificationResponse)
async def verify_policy(
    policy_id: uuid.UUID,
    request: VerificationRequest,
    db: Session = Depends(get_db)
):
    """Verify a Q&A pair against a compiled policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Get latest compilation
    latest_compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    
    if not latest_compilation:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before verification. Please compile the policy first."
        )
    
    try:
        # Extract variables from Q&A pair
        print(f"Debug: Starting variable extraction for policy {policy_id}")
        try:
            extracted_variables = await variable_extractor.extract_variables(
                request.question,
                request.answer,
                policy.variables or []
            )
            print(f"Debug: Variable extraction successful, extracted: {len(extracted_variables)} variables")
        except Exception as e:
            print(f"Debug: Variable extraction failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Variable extraction failed: {str(e)}")
        
        # Verify using Z3
        print(f"Debug: Starting Z3 verification")
        try:
            verification_result = verification_service.verify_scenario(
                extracted_variables,
                latest_compilation.z3_constraints,
                policy.rules or []
            )
            print(f"Debug: Z3 verification successful, result: {verification_result.get('result', 'unknown')}")
        except Exception as e:
            print(f"Debug: Z3 verification failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Z3 verification failed: {str(e)}")
        
        # Determine result enum (handle both enum values and legacy string values)
        print(f"Debug: Mapping result '{verification_result['result']}' to enum")
        try:
            result_value = verification_result['result']
            if isinstance(result_value, VerificationResult):
                result_enum = result_value
            elif result_value == VerificationResult.VALID.value or result_value == 'valid':
                result_enum = VerificationResult.VALID
            elif result_value == VerificationResult.INVALID.value or result_value == 'invalid':
                result_enum = VerificationResult.INVALID
            elif result_value == VerificationResult.NEEDS_CLARIFICATION.value or result_value == 'needs_clarification':
                result_enum = VerificationResult.NEEDS_CLARIFICATION
            else:
                result_enum = VerificationResult.ERROR
            print(f"Debug: Enum mapping successful: {result_enum}")
        except Exception as e:
            print(f"Debug: Enum mapping failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Result enum mapping failed: {str(e)}")
        
        # Store verification in database
        try:
            verification = Verification(
                policy_id=policy_id,
                question=request.question,
                answer=request.answer,
                extracted_variables=extracted_variables,
                verification_result=result_enum.value,  # Use .value to get the string value
                explanation=verification_result['explanation'],
                suggestions=verification_result['suggestions']
            )
            
            db.add(verification)
            db.commit()
            db.refresh(verification)
        except Exception as db_error:
            print(f"Database error: {str(db_error)}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
        return VerificationResponse(
            verification_id=verification.id,
            result=result_enum,
            extracted_variables=extracted_variables,
            explanation=verification_result['explanation'],
            suggestions=verification_result['suggestions']
        )
        
    except Exception as e:
        # Store failed verification with rollback handling
        try:
            verification = Verification(
                policy_id=policy_id,
                question=request.question,
                answer=request.answer,
                extracted_variables={},
                verification_result=VerificationResult.ERROR.value,  # Use .value to get the string value
                explanation=f"Verification failed: {str(e)}",
                suggestions=[]
            )
            
            db.add(verification)
            db.commit()
            db.refresh(verification)
        except Exception as db_error:
            print(f"Database error in exception handler: {str(db_error)}")
            db.rollback()
            # Continue with the original error response even if DB logging fails
        
        return VerificationResponse(
            verification_id=getattr(verification, 'id', uuid.uuid4()) if 'verification' in locals() else uuid.uuid4(),
            result=VerificationResult.ERROR,
            extracted_variables={},
            explanation=f"Verification failed: {str(e)}",
            suggestions=["Please check the policy compilation and try again"]
        )

@router.get("/{policy_id}/verifications", response_model=List[VerificationHistoryResponse])
async def get_verification_history(
    policy_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    result_filter: str = None,
    db: Session = Depends(get_db)
):
    """Get verification history for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    query = db.query(Verification).filter(Verification.policy_id == policy_id)
    
    # Apply result filter if provided
    if result_filter:
        if result_filter not in ['valid', 'invalid', 'error']:
            raise HTTPException(status_code=400, detail="Invalid result filter. Use: valid, invalid, or error")
        query = query.filter(Verification.verification_result == result_filter)
    
    verifications = (
        query
        .order_by(Verification.verified_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return verifications

@router.get("/verifications/{verification_id}", response_model=VerificationHistoryResponse)
async def get_verification_details(verification_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get details of a specific verification"""
    
    verification = db.query(Verification).filter(Verification.id == verification_id).first()
    
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")
    
    return verification

@router.delete("/{policy_id}/verifications")
async def clear_verification_history(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Clear all verification history for a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Delete all verifications for this policy
    deleted_count = (
        db.query(Verification)
        .filter(Verification.policy_id == policy_id)
        .delete()
    )
    
    db.commit()
    
    return {"message": f"Deleted {deleted_count} verification records"}

@router.post("/{policy_id}/test-extraction")
async def test_variable_extraction(
    policy_id: uuid.UUID,
    request: VerificationRequest,
    db: Session = Depends(get_db)
):
    """Test variable extraction without performing verification"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    try:
        # Extract variables from Q&A pair
        extracted_variables = await variable_extractor.extract_variables(
            request.question,
            request.answer,
            policy.variables or []
        )
        
        # Validate extracted variables
        validation_errors = await variable_extractor.validate_extracted_variables(
            extracted_variables,
            policy.variables or []
        )
        
        return {
            "extracted_variables": extracted_variables,
            "validation_errors": validation_errors,
            "success": len(validation_errors) == 0
        }
        
    except Exception as e:
        return {
            "extracted_variables": {},
            "validation_errors": [str(e)],
            "success": False
        }

@router.post("/{policy_id}/batch-verify")
async def batch_verify(
    policy_id: uuid.UUID,
    requests: List[VerificationRequest],
    db: Session = Depends(get_db)
):
    """Verify multiple Q&A pairs against a policy"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Get latest compilation
    latest_compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    
    if not latest_compilation:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before verification. Please compile the policy first."
        )
    
    results = []
    
    for request in requests:
        try:
            # Extract variables
            extracted_variables = await variable_extractor.extract_variables(
                request.question,
                request.answer,
                policy.variables or []
            )
            
            # Verify
            verification_result = verification_service.verify_scenario(
                extracted_variables,
                latest_compilation.z3_constraints,
                policy.rules or []
            )
            
            # Determine result enum for batch processing
            if verification_result['result'] == 'valid':
                batch_result_enum = VerificationResult.VALID
            elif verification_result['result'] == 'invalid':
                batch_result_enum = VerificationResult.INVALID
            elif verification_result['result'] == 'needs_clarification':
                batch_result_enum = VerificationResult.NEEDS_CLARIFICATION
            else:
                batch_result_enum = VerificationResult.ERROR
                
            # Store in database
            verification = Verification(
                policy_id=policy_id,
                question=request.question,
                answer=request.answer,
                extracted_variables=extracted_variables,
                verification_result=batch_result_enum.value,  # Use .value to get the string value
                explanation=verification_result['explanation'],
                suggestions=verification_result['suggestions']
            )
            
            db.add(verification)
            
            results.append({
                "question": request.question,
                "answer": request.answer,
                "result": verification_result['result'],
                "extracted_variables": extracted_variables,
                "explanation": verification_result['explanation'],
                "suggestions": verification_result['suggestions']
            })
            
        except Exception as e:
            results.append({
                "question": request.question,
                "answer": request.answer,
                "result": "error",
                "extracted_variables": {},
                "explanation": f"Verification failed: {str(e)}",
                "suggestions": []
            })
    
    db.commit()
    
    return {
        "total_processed": len(requests),
        "results": results,
        "summary": {
            "valid": len([r for r in results if r['result'] == 'valid']),
            "invalid": len([r for r in results if r['result'] == 'invalid']),
            "errors": len([r for r in results if r['result'] == 'error'])
        }
    } 