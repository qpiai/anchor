from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from ..core.database import get_db
from ..models.database import Policy, Verification, VerificationResult
from ..models.schemas import (
    VerificationRequest, VerificationResponse, VerificationHistoryResponse
)
from ..services.decision import (
    PolicyNotCompiledError, PolicyNotFoundError, decide, load_compiled_policy, summarize,
)
from ..services.extraction import get_variable_extractor
from ..services.jev_extractor import ExtractorUnavailableError

router = APIRouter(prefix="/policies", tags=["verification"])


@router.post("/{policy_id}/verify", response_model=VerificationResponse)
async def verify_policy(
    policy_id: uuid.UUID,
    request: VerificationRequest,
    db: Session = Depends(get_db)
):
    """Verify a Q&A pair against a compiled policy"""
    policy, compilation = _load_or_http(db, policy_id)
    try:
        outcome = await decide(db, policy, compilation, request.question, request.answer, facts=request.facts)
    except ExtractorUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return VerificationResponse(
        verification_id=outcome["verification_id"],
        result=outcome["result"],
        extracted_variables=outcome["extracted_variables"],
        explanation=outcome["explanation"],
        suggestions=outcome["suggestions"],
        details=outcome["details"],
    )


def _load_or_http(db: Session, policy_id: uuid.UUID):
    try:
        return load_compiled_policy(db, policy_id)
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PolicyNotCompiledError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
        wanted = result_filter.upper()
        if wanted not in {item.value for item in VerificationResult}:
            raise HTTPException(
                status_code=400,
                detail="Invalid result filter. Use: valid, invalid, needs_clarification, or error",
            )
        query = query.filter(Verification.verification_result == wanted)
    
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
        variable_extractor = get_variable_extractor()
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
    policy, compilation = _load_or_http(db, policy_id)
    results = []
    for request in requests:
        try:
            outcome = await decide(
                db, policy, compilation, request.question, request.answer, commit=False, facts=request.facts
            )
        except ExtractorUnavailableError as exc:
            db.commit()
            raise HTTPException(status_code=503, detail=str(exc))
        results.append({
            "question": request.question,
            "answer": request.answer,
            "verification_id": str(outcome["verification_id"]),
            "result": outcome["result"],
            "extracted_variables": outcome["extracted_variables"],
            "explanation": outcome["explanation"],
            "suggestions": outcome["suggestions"],
            "details": outcome["details"],
        })
    db.commit()
    return {"total_processed": len(requests), "results": results, "summary": summarize(results)}
