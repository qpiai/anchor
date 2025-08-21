from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import uuid
from pydantic import BaseModel

from ..core.database import get_db
from ..models.database import Policy, PolicyCompilation
from ..models.schemas import VerificationRequest
from ..services.clarifying_questions import ClarifyingQuestionService
from ..services.variable_extractor import VariableExtractorService
from ..services.verification import VerificationService

router = APIRouter(prefix="/policies", tags=["clarifying_questions"])

# Initialize services
clarifying_service = ClarifyingQuestionService()
variable_extractor = VariableExtractorService()
verification_service = VerificationService()

class ClarifyingQuestionsRequest(BaseModel):
    question: str
    answer: str
    
class ClarifyingResponseRequest(BaseModel):
    original_question: str
    original_answer: str
    clarifying_responses: List[Dict[str, str]]  # [{"question": "...", "answer": "..."}]

@router.post("/{policy_id}/clarifying-questions")
async def get_clarifying_questions(
    policy_id: uuid.UUID,
    request: ClarifyingQuestionsRequest,
    db: Session = Depends(get_db)
):
    """Get clarifying questions when initial verification needs more information"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    try:
        # First try to extract variables from the original Q&A
        extracted_variables = await variable_extractor.extract_variables(
            request.question,
            request.answer,
            policy.variables or []
        )
        
        # Prepare policy context
        policy_dict = {
            "policy_name": policy.name,
            "domain": policy.domain,
            "description": policy.description,
            "variables": policy.variables or [],
            "rules": policy.rules or [],
            "constraints": policy.constraints or []
        }
        
        # Determine why clarification is needed
        if len(extracted_variables) == 0:
            issue = "Unable to extract any variables from the provided Q&A"
        else:
            # Check if we have enough for verification
            required_vars = {var['name'] for var in policy.variables or []}
            missing_vars = required_vars - set(extracted_variables.keys())
            if missing_vars:
                issue = f"Missing critical variables: {', '.join(missing_vars)}"
            else:
                issue = "Variables extracted but verification result unclear"
        
        verification_context = {
            'result': 'needs_clarification',
            'issue': issue,
            'question': request.question,
            'answer': request.answer
        }
        
        # Generate clarifying questions using LLM
        questions = await clarifying_service.generate_clarifying_questions(
            policy_dict,
            extracted_variables,
            verification_context
        )
        
        return {
            "status": "needs_clarification",
            "extracted_variables": extracted_variables,
            "issue": issue,
            "clarifying_questions": questions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate clarifying questions: {str(e)}")

@router.post("/{policy_id}/verify-with-clarification")
async def verify_with_clarifying_responses(
    policy_id: uuid.UUID,
    request: ClarifyingResponseRequest,
    db: Session = Depends(get_db)
):
    """Verify policy after receiving responses to clarifying questions"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Check if policy is compiled
    latest_compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .filter(PolicyCompilation.compilation_status == "success")
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    
    if not latest_compilation:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before verification."
        )
    
    try:
        # Process the clarifying responses to extract enhanced variables
        enhanced_variables = await clarifying_service.process_clarifying_response(
            request.original_question,
            request.original_answer,
            request.clarifying_responses,
            policy.variables or []
        )
        
        # If we still don't have enough information, return more questions
        if len(enhanced_variables) == 0:
            return {
                "status": "still_needs_clarification",
                "message": "The provided responses did not yield sufficient information for verification.",
                "suggestion": "Please provide more specific details about the scenario."
            }
        
        # Perform verification with enhanced variables
        verification_result = verification_service.verify_scenario(
            enhanced_variables,
            latest_compilation.z3_constraints,
            policy.rules or []
        )
        
        # Store verification in database
        from ..models.database import Verification, VerificationResult
        
        if verification_result['result'] == 'valid':
            result_enum = VerificationResult.VALID
        elif verification_result['result'] == 'invalid':
            result_enum = VerificationResult.INVALID
        elif verification_result['result'] == 'needs_clarification':
            result_enum = VerificationResult.NEEDS_CLARIFICATION
        else:
            result_enum = VerificationResult.ERROR
        
        # Create combined question/answer text for storage
        combined_qa = f"Original Q: {request.original_question}\nA: {request.original_answer}\n\n"
        combined_qa += "Clarifying Q&A:\n"
        for i, qa in enumerate(request.clarifying_responses):
            combined_qa += f"Q{i+1}: {qa['question']}\nA{i+1}: {qa['answer']}\n"
        
        verification = Verification(
            policy_id=policy_id,
            question=request.original_question,
            answer=combined_qa,
            extracted_variables=enhanced_variables,
            verification_result=result_enum,
            explanation=verification_result['explanation'],
            suggestions=verification_result['suggestions']
        )
        
        db.add(verification)
        db.commit()
        db.refresh(verification)
        
        return {
            "verification_id": verification.id,
            "result": verification_result['result'],
            "extracted_variables": enhanced_variables,
            "explanation": verification_result['explanation'],
            "suggestions": verification_result['suggestions']
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

@router.post("/{policy_id}/smart-verify")
async def smart_verify(
    policy_id: uuid.UUID,
    request: VerificationRequest,
    db: Session = Depends(get_db)
):
    """Intelligent verification that automatically handles clarifying questions flow"""
    
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Check if policy is compiled
    latest_compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .filter(PolicyCompilation.compilation_status == "success")
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    
    if not latest_compilation:
        raise HTTPException(
            status_code=400, 
            detail="Policy must be compiled before verification."
        )
    
    try:
        # Step 1: Extract variables
        extracted_variables = await variable_extractor.extract_variables(
            request.question,
            request.answer,
            policy.variables or []
        )
        
        # Step 2: Attempt verification
        verification_result = verification_service.verify_scenario(
            extracted_variables,
            latest_compilation.z3_constraints,
            policy.rules or []
        )
        
        # Step 3: If result is definitive, return it
        if verification_result['result'] in ['valid', 'invalid']:
            # Store in database
            from ..models.database import Verification, VerificationResult
            
            result_enum = VerificationResult.VALID if verification_result['result'] == 'valid' else VerificationResult.INVALID
            
            verification = Verification(
                policy_id=policy_id,
                question=request.question,
                answer=request.answer,
                extracted_variables=extracted_variables,
                verification_result=result_enum,
                explanation=verification_result['explanation'],
                suggestions=verification_result['suggestions']
            )
            
            db.add(verification)
            db.commit()
            db.refresh(verification)
            
            return {
                "verification_id": verification.id,
                "result": verification_result['result'],
                "extracted_variables": extracted_variables,
                "explanation": verification_result['explanation'],
                "suggestions": verification_result['suggestions'],
                "needs_clarification": False
            }
        
        # Step 4: If needs clarification, generate questions
        else:
            policy_dict = {
                "policy_name": policy.name,
                "domain": policy.domain,
                "description": policy.description,
                "variables": policy.variables or [],
                "rules": policy.rules or [],
                "constraints": policy.constraints or []
            }
            
            verification_context = {
                'result': 'needs_clarification',
                'issue': 'Insufficient information for definitive verification',
                'question': request.question,
                'answer': request.answer
            }
            
            clarifying_questions = await clarifying_service.generate_clarifying_questions(
                policy_dict,
                extracted_variables,
                verification_context
            )
            
            return {
                "result": "needs_clarification",
                "extracted_variables": extracted_variables,
                "explanation": "Additional information needed to complete verification",
                "clarifying_questions": clarifying_questions,
                "needs_clarification": True
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Smart verification failed: {str(e)}")