from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime

from ..core.database import get_db
from ..models.database import Policy, PolicyDocument
from ..models.schemas import (
    PolicyResponse, PolicyCreate, PolicyUpdate, PolicyStatusResponse,
    ErrorResponse
)

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
        policy.status = "draft"
    
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