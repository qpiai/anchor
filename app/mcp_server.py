import logging
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from .core.database import SessionLocal
from .models.database import CompilationStatus, Policy, PolicyCompilation, Verification
from .services.decision import (
    PolicyNotCompiledError,
    PolicyNotFoundError,
    decide,
    load_compiled_policy,
    summarize,
)
from .services.jev_extractor import ExtractorUnavailableError

# Logs go to stderr; stdout is the MCP STDIO channel.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

mcp = FastMCP("Anchor Policy Verification Server")


@contextmanager
def _session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _facts(outcome: dict) -> Dict[str, Any]:
    details = outcome.get("details") or {}
    confidence = details.get("confidence") or {}
    facts = {}
    for name, value in (outcome.get("extracted_variables") or {}).items():
        stated = value not in ("MISSING_MANDATORY", "SKIP_RULE")
        facts[name] = {"value": value if stated else None, "confidence": confidence.get(name)}
    return facts


def _decision_payload(outcome: dict) -> Dict[str, Any]:
    details = outcome.get("details") or {}
    return {
        "success": outcome["result"] != "ERROR",
        "verification_id": str(outcome["verification_id"]),
        "result": outcome["result"],
        "explanation": outcome["explanation"],
        "suggestions": outcome["suggestions"],
        "facts": _facts(outcome),
        "missing_facts": details.get("missing_mandatory_vars") or [],
        "failed_rules": details.get("failed_rules") or [],
        "flags": details.get("flags") or {},
        "extractor": details.get("extractor"),
        "fallback_used": details.get("fallback_used", False),
        "latency_ms": details.get("latency_ms"),
    }


def _error(message: str, **extra) -> Dict[str, Any]:
    return {"success": False, "result": "ERROR", "explanation": message, **extra}


def _load(db: Session, policy_id: str):
    return load_compiled_policy(db, uuid.UUID(policy_id))


@mcp.tool
def list_policies() -> Dict[str, Any]:
    """
    List compiled policies that can be used for verification.
    Returns each policy's id, name, description, domain, and variable/rule counts.
    """
    with _session() as db:
        policies = (
            db.query(Policy)
            .filter(
                Policy.id.in_(
                    db.query(PolicyCompilation.policy_id).filter(
                        PolicyCompilation.compilation_status == CompilationStatus.SUCCESS
                    )
                )
            )
            .order_by(Policy.created_at.desc())
            .all()
        )
        items = [
            {
                "id": str(policy.id),
                "name": policy.name,
                "description": policy.description or "",
                "domain": policy.domain,
                "created_at": policy.created_at.isoformat(),
                "variable_count": len(policy.variables or []),
                "rule_count": len(policy.rules or []),
            }
            for policy in policies
        ]
    return {"success": True, "policies": items, "total_count": len(items)}


@mcp.tool
async def verify_response(
    policy_id: str, question: str, answer: str = "", facts: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Decide whether a request is allowed under a compiled policy.

    `question` is the request (for an AI agent: the action it wants to take and why).
    `answer` is optional context or the proposed answer/action details.
    `facts` is optional {variable: value} from trusted systems (approval log, identity check, HR record).
    Trusted facts override the text; variables marked trusted_only are never read from the text.

    Facts are extracted with per-fact confidence, then the Z3 solver decides.
    Returns result VALID, INVALID, NEEDS_CLARIFICATION, or ERROR, plus the explanation,
    clarifying questions (suggestions), extracted facts, missing facts, failed rules,
    guard flags (out_of_scope, injection_suspected), and a verification_id for the audit log.
    Treat anything other than VALID as "do not proceed".
    """
    try:
        with _session() as db:
            policy, compilation = _load(db, policy_id)
            outcome = await decide(db, policy, compilation, question, answer, facts=facts)
            return _decision_payload(outcome)
    except ValueError:
        return _error(f"Invalid policy ID format: {policy_id}")
    except (PolicyNotFoundError, PolicyNotCompiledError) as exc:
        return _error(str(exc))
    except ExtractorUnavailableError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("verify_response failed")
        return _error(f"Verification failed: {exc}")


@mcp.tool
async def batch_verify(policy_id: str, qa_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verify several requests against one policy. Each item is {"question": ..., "answer": ..., "facts": {...}}.
    Returns per-item decisions (same shape as verify_response) and a summary count.
    """
    try:
        with _session() as db:
            policy, compilation = _load(db, policy_id)
            results = []
            for index, pair in enumerate(qa_pairs):
                outcome = await decide(
                    db, policy, compilation, pair.get("question", ""), pair.get("answer", ""), commit=False,
                    facts=pair.get("facts"),
                )
                results.append({"index": index, **_decision_payload(outcome)})
            db.commit()
        return {"success": True, "results": results, "summary": summarize(results)}
    except ValueError:
        return _error(f"Invalid policy ID format: {policy_id}", results=[])
    except (PolicyNotFoundError, PolicyNotCompiledError, ExtractorUnavailableError) as exc:
        return _error(str(exc), results=[])
    except Exception as exc:
        logger.exception("batch_verify failed")
        return _error(f"Batch verification failed: {exc}", results=[])


@mcp.tool
def get_policy_info(policy_id: str) -> Dict[str, Any]:
    """
    Get a policy's variables (facts it needs), rules, and compilation status.
    Useful before verification to know which facts to state in the request.
    """
    try:
        with _session() as db:
            policy = db.query(Policy).filter(Policy.id == uuid.UUID(policy_id)).first()
            if not policy:
                return {"success": False, "error": f"Policy with ID {policy_id} not found"}
            compilation = (
                db.query(PolicyCompilation)
                .filter(PolicyCompilation.policy_id == policy.id)
                .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
                .order_by(PolicyCompilation.compiled_at.desc())
                .first()
            )
            return {
                "success": True,
                "policy": {
                    "id": str(policy.id),
                    "name": policy.name,
                    "description": policy.description or "",
                    "domain": policy.domain,
                    "created_at": policy.created_at.isoformat(),
                    "updated_at": policy.updated_at.isoformat(),
                    "is_compiled": compilation is not None,
                    "compiled_at": compilation.compiled_at.isoformat() if compilation else None,
                    "variables": policy.variables or [],
                    "rules": policy.rules or [],
                },
            }
    except ValueError:
        return {"success": False, "error": f"Invalid policy ID format: {policy_id}"}


@mcp.tool
def get_verification(verification_id: str) -> Dict[str, Any]:
    """
    Look up a past decision from the audit log by verification_id: request, verdict,
    explanation, extracted facts, and details (confidence, rule trace, latency, extractor).
    """
    try:
        with _session() as db:
            row = db.query(Verification).filter(Verification.id == uuid.UUID(verification_id)).first()
            if not row:
                return {"success": False, "error": f"Verification {verification_id} not found"}
            return {
                "success": True,
                "verification": {
                    "id": str(row.id),
                    "policy_id": str(row.policy_id),
                    "question": row.question,
                    "answer": row.answer,
                    "result": row.verification_result,
                    "explanation": row.explanation,
                    "suggestions": row.suggestions or [],
                    "extracted_variables": row.extracted_variables or {},
                    "details": row.details,
                    "verified_at": row.verified_at.isoformat() if row.verified_at else None,
                },
            }
    except ValueError:
        return {"success": False, "error": f"Invalid verification ID format: {verification_id}"}


if __name__ == "__main__":
    logger.info("Starting Anchor Policy Verification MCP Server...")
    mcp.run()
