"""On-demand rule grounding against the source document."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from ..core.database import get_db
from ..models.database import Policy
from ..services.grounding import check_rules
from ..services.jev_extractor import ExtractorUnavailableError

router = APIRouter(prefix="/policies", tags=["grounding"])


@router.get("/{policy_id}/grounding")
async def ground_policy(policy_id: uuid.UUID, db: Session = Depends(get_db)):
    """Score each rule against the most relevant source passage. Advisory only."""
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    document = policy.document
    source = (document.content if document is not None else "") or (policy.description or "")
    if not source.strip():
        raise HTTPException(status_code=400, detail="Policy has no source text to ground rules against")
    try:
        return await check_rules(
            str(policy.id),
            policy.rules or [],
            source,
            updated_at=policy.updated_at,
        )
    except ExtractorUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Rule grounding is unavailable: {type(exc).__name__}") from exc
