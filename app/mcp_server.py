import asyncio
import logging
import uuid
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .core.database import get_db
from .core.config import settings
from .models.database import Policy, PolicyCompilation, CompilationStatus
from .models.schemas import VerificationResult
from .services.verification import VerificationService
from .services.variable_extractor import VariableExtractorService

# Configure logging to stderr (required for MCP STDIO transport)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize services
verification_service = VerificationService()
variable_extractor = VariableExtractorService()

# Create MCP server
mcp = FastMCP("Anchor Policy Verification Server")

# Keep Pydantic models for documentation but use individual parameters in tools

@mcp.tool
def list_policies() -> Dict[str, Any]:
    """
    List all available compiled policies that can be used for verification.
    Returns policies with their IDs, names, domains, and compilation status.
    """
    try:
        db = next(get_db())

        # Get all policies with successful compilations
        policies = db.query(Policy).join(PolicyCompilation).filter(
            PolicyCompilation.compilation_status == CompilationStatus.SUCCESS
        ).all()

        result = []
        for policy in policies:
            result.append({
                "id": str(policy.id),
                "name": policy.name,
                "description": policy.description or "",
                "domain": policy.domain,
                "created_at": policy.created_at.isoformat(),
                "variable_count": len(policy.variables) if policy.variables else 0,
                "rule_count": len(policy.rules) if policy.rules else 0
            })

        db.close()

        return {
            "success": True,
            "policies": result,
            "total_count": len(result)
        }

    except Exception as e:
        logger.error(f"Error listing policies: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to list policies: {str(e)}",
            "policies": []
        }

@mcp.tool
async def verify_response(policy_id: str, question: str, answer: str) -> Dict[str, Any]:
    """
    Verify a question-answer pair against a compiled policy.

    This tool takes a policy ID, question, and answer, then:
    1. Extracts variables from the Q&A pair
    2. Verifies the scenario against the policy's Z3 constraints
    3. Returns verification result with explanation

    Returns:
    - result: "valid", "invalid", "needs_clarification", or "error"
    - explanation: Human-readable explanation of the result
    - extracted_variables: Variables extracted from the Q&A pair
    - suggestions: List of clarifying questions if needed
    """
    try:
        db = next(get_db())

        # Validate policy exists and is compiled
        policy_uuid = uuid.UUID(policy_id)
        policy = db.query(Policy).filter(Policy.id == policy_uuid).first()

        if not policy:
            db.close()
            return {
                "success": False,
                "result": "error",
                "explanation": f"Policy with ID {policy_id} not found",
                "extracted_variables": {},
                "suggestions": []
            }

        # Get latest successful compilation
        latest_compilation = (
            db.query(PolicyCompilation)
            .filter(PolicyCompilation.policy_id == policy_uuid)
            .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
            .order_by(PolicyCompilation.compiled_at.desc())
            .first()
        )

        if not latest_compilation:
            db.close()
            return {
                "success": False,
                "result": "error",
                "explanation": f"Policy {policy.name} is not compiled. Please compile the policy first.",
                "extracted_variables": {},
                "suggestions": ["Compile the policy before attempting verification"]
            }

        # Extract variables from Q&A pair
        try:
            extracted_variables = await variable_extractor.extract_variables(
                question,
                answer,
                policy.variables or []
            )
        except Exception as e:
            db.close()
            return {
                "success": False,
                "result": "error",
                "explanation": f"Variable extraction failed: {str(e)}",
                "extracted_variables": {},
                "suggestions": ["Check that the question and answer are properly formatted"]
            }

        # Verify using Z3
        try:
            verification_result = verification_service.verify_scenario(
                extracted_variables,
                latest_compilation.z3_constraints,
                policy.rules or []
            )
        except Exception as e:
            db.close()
            return {
                "success": False,
                "result": "error",
                "explanation": f"Z3 verification failed: {str(e)}",
                "extracted_variables": extracted_variables,
                "suggestions": ["Check policy compilation and try again"]
            }

        db.close()

        return {
            "success": True,
            "result": verification_result.get('result', 'error'),
            "explanation": verification_result.get('explanation', 'No explanation provided'),
            "extracted_variables": extracted_variables,
            "suggestions": verification_result.get('suggestions', [])
        }

    except ValueError as e:
        return {
            "success": False,
            "result": "error",
            "explanation": f"Invalid policy ID format: {str(e)}",
            "extracted_variables": {},
            "suggestions": ["Provide a valid UUID for the policy ID"]
        }
    except Exception as e:
        logger.error(f"Error in verify_response: {str(e)}")
        return {
            "success": False,
            "result": "error",
            "explanation": f"Verification failed: {str(e)}",
            "extracted_variables": {},
            "suggestions": ["Check the input parameters and try again"]
        }

@mcp.tool
async def batch_verify(policy_id: str, qa_pairs: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Verify multiple question-answer pairs against a single policy.

    This tool processes multiple Q&A pairs in batch for efficiency.
    Returns summary statistics and individual results for each pair.
    """
    try:
        db = next(get_db())

        # Validate policy exists and is compiled
        policy_uuid = uuid.UUID(policy_id)
        policy = db.query(Policy).filter(Policy.id == policy_uuid).first()

        if not policy:
            db.close()
            return {
                "success": False,
                "error": f"Policy with ID {policy_id} not found",
                "results": [],
                "summary": {"total": 0, "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}
            }

        # Get latest successful compilation
        latest_compilation = (
            db.query(PolicyCompilation)
            .filter(PolicyCompilation.policy_id == policy_uuid)
            .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
            .order_by(PolicyCompilation.compiled_at.desc())
            .first()
        )

        if not latest_compilation:
            db.close()
            return {
                "success": False,
                "error": f"Policy {policy.name} is not compiled",
                "results": [],
                "summary": {"total": 0, "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}
            }

        results = []
        summary = {"total": len(qa_pairs), "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}

        for i, qa_pair in enumerate(qa_pairs):
            question = qa_pair.get("question", "")
            answer = qa_pair.get("answer", "")

            try:
                # Extract variables
                extracted_variables = await variable_extractor.extract_variables(
                    question,
                    answer,
                    policy.variables or []
                )

                # Verify
                verification_result = verification_service.verify_scenario(
                    extracted_variables,
                    latest_compilation.z3_constraints,
                    policy.rules or []
                )

                result = verification_result.get('result', 'error')
                summary[result] = summary.get(result, 0) + 1

                results.append({
                    "index": i,
                    "question": question,
                    "answer": answer,
                    "result": result,
                    "explanation": verification_result.get('explanation', ''),
                    "extracted_variables": extracted_variables,
                    "suggestions": verification_result.get('suggestions', [])
                })

            except Exception as e:
                summary["errors"] += 1
                results.append({
                    "index": i,
                    "question": question,
                    "answer": answer,
                    "result": "error",
                    "explanation": f"Verification failed: {str(e)}",
                    "extracted_variables": {},
                    "suggestions": []
                })

        db.close()

        return {
            "success": True,
            "results": results,
            "summary": summary
        }

    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid policy ID format: {str(e)}",
            "results": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}
        }
    except Exception as e:
        logger.error(f"Error in batch_verify: {str(e)}")
        return {
            "success": False,
            "error": f"Batch verification failed: {str(e)}",
            "results": [],
            "summary": {"total": 0, "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}
        }

@mcp.tool
def get_policy_info(policy_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a policy including its variables, rules, and metadata.

    This is useful for understanding what variables and rules a policy contains
    before attempting verification.
    """
    try:
        db = next(get_db())

        policy_uuid = uuid.UUID(policy_id)
        policy = db.query(Policy).filter(Policy.id == policy_uuid).first()

        if not policy:
            db.close()
            return {
                "success": False,
                "error": f"Policy with ID {policy_id} not found"
            }

        # Check compilation status
        latest_compilation = (
            db.query(PolicyCompilation)
            .filter(PolicyCompilation.policy_id == policy_uuid)
            .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
            .order_by(PolicyCompilation.compiled_at.desc())
            .first()
        )

        db.close()

        return {
            "success": True,
            "policy": {
                "id": str(policy.id),
                "name": policy.name,
                "description": policy.description or "",
                "domain": policy.domain,
                "created_at": policy.created_at.isoformat(),
                "updated_at": policy.updated_at.isoformat(),
                "is_compiled": latest_compilation is not None,
                "compiled_at": latest_compilation.compiled_at.isoformat() if latest_compilation else None,
                "variables": policy.variables or [],
                "rules": policy.rules or [],
                "examples": policy.examples or []
            }
        }

    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid policy ID format: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error in get_policy_info: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to get policy info: {str(e)}"
        }

if __name__ == "__main__":
    # Run the MCP server
    logger.info("Starting Anchor Policy Verification MCP Server...")
    mcp.run()