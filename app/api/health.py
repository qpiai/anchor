from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import asyncio

from ..core.database import get_db
from ..core.config import settings
from ..models.schemas import HealthResponse
from ..services.policy_generator import PolicyGeneratorService
from ..services.variable_extractor import VariableExtractorService

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint to verify all system components"""
    
    components = {}
    overall_status = "healthy"
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"
        overall_status = "unhealthy"
    
    # Check LLM services
    try:
        policy_generator = PolicyGeneratorService()
        if policy_generator.openai_client:
            components["openai"] = "configured"
        else:
            components["openai"] = "not configured"
        
        if policy_generator.anthropic_client:
            components["anthropic"] = "configured"
        else:
            components["anthropic"] = "not configured"
        
        # At least one LLM service should be configured
        if not policy_generator.openai_client and not policy_generator.anthropic_client:
            components["llm_services"] = "no LLM service configured"
            overall_status = "degraded"
        else:
            components["llm_services"] = "healthy"
    
    except Exception as e:
        components["llm_services"] = f"error: {str(e)}"
        overall_status = "unhealthy"
    
    # Check Z3 solver
    try:
        from z3 import Solver, IntVal
        solver = Solver()
        x = IntVal(1)
        solver.add(x == 1)
        if solver.check().r == 1:  # SAT
            components["z3_solver"] = "healthy"
        else:
            components["z3_solver"] = "unexpected result"
            overall_status = "degraded"
    except Exception as e:
        components["z3_solver"] = f"unhealthy: {str(e)}"
        overall_status = "unhealthy"
    
    # Check file system
    try:
        import os
        os.makedirs(settings.upload_dir, exist_ok=True)
        if os.path.exists(settings.upload_dir) and os.access(settings.upload_dir, os.W_OK):
            components["file_system"] = "healthy"
        else:
            components["file_system"] = "upload directory not writable"
            overall_status = "degraded"
    except Exception as e:
        components["file_system"] = f"unhealthy: {str(e)}"
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        components=components
    )

@router.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "description": "Anchor - Multi-agent AI system for policy verification",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": settings.api_v1_prefix
    }

@router.get("/status")
async def system_status(db: Session = Depends(get_db)):
    """Get detailed system status and statistics"""
    
    try:
        from ..models.database import PolicyDocument, Policy, PolicyCompilation, Verification
        
        # Get database statistics
        stats = {}
        
        stats["documents"] = {
            "total": db.query(PolicyDocument).count(),
            "by_domain": {}
        }
        
        # Documents by domain
        domain_counts = db.execute(text("""
            SELECT domain, COUNT(*) as count 
            FROM policy_documents 
            GROUP BY domain
        """)).fetchall()
        
        for domain, count in domain_counts:
            stats["documents"]["by_domain"][domain] = count
        
        stats["policies"] = {
            "total": db.query(Policy).count(),
            "by_status": {}
        }
        
        # Policies by status
        status_counts = db.execute(text("""
            SELECT status, COUNT(*) as count 
            FROM policies 
            GROUP BY status
        """)).fetchall()
        
        for status, count in status_counts:
            stats["policies"]["by_status"][status] = count
        
        stats["compilations"] = {
            "total": db.query(PolicyCompilation).count(),
            "successful": db.query(PolicyCompilation).filter(
                PolicyCompilation.compilation_status == "success"
            ).count()
        }
        
        stats["verifications"] = {
            "total": db.query(Verification).count(),
            "by_result": {}
        }
        
        # Verifications by result
        result_counts = db.execute(text("""
            SELECT verification_result, COUNT(*) as count 
            FROM verifications 
            GROUP BY verification_result
        """)).fetchall()
        
        for result, count in result_counts:
            stats["verifications"]["by_result"][result] = count
        
        return {
            "status": "operational",
            "statistics": stats,
            "uptime": "N/A",  # Could implement actual uptime tracking
            "version": "1.0.0"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")

@router.get("/config")
async def get_configuration():
    """Get public configuration information"""
    
    return {
        "app_name": settings.app_name,
        "debug": settings.debug,
        "max_file_size": settings.max_file_size,
        "upload_dir": settings.upload_dir,
        "default_llm_provider": settings.default_llm_provider,
        "openai_configured": bool(settings.openai_api_key),
        "anthropic_configured": bool(settings.anthropic_api_key),
        "supported_file_types": [".pdf", ".docx", ".doc", ".txt"],
        "api_version": "1.0.0"
    } 