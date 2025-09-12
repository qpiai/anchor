from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .core.config import settings
from .core.database import create_tables
from .api import documents, policies, compilation, verification, health

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Anchor...")
    
    # Create database tables
    create_tables()
    logger.info("Database tables created/verified")
    
    # Create upload directory
    import os
    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info(f"Upload directory ensured: {settings.upload_dir}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Anchor...")

# Create FastAPI application
app = FastAPI(
    title="Anchor",
    description="""
    Multi-agent AI system for autonomous policy generation and verification.
    
    ## Features
    - **Document Upload**: Upload policy documents (PDF, DOCX, TXT)
    - **Policy Generation**: AI-powered policy creation from documents
    - **Rule Compilation**: Convert policies to formal Z3 logic constraints
    - **Variable Extraction**: Extract variables from natural language Q&A
    - **Formal Verification**: Mathematical verification using Z3 solver
    - **Policy Management**: CRUD operations for policies and compilations
    
    ## Workflow
    1. Upload a policy document
    2. AI generates structured policy with variables and rules
    3. Compile policy to formal Z3 constraints
    4. Ask questions and get verified answers
    
    ## API Documentation
    Visit `/docs` for interactive API documentation or `/redoc` for alternative docs.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(documents.router, prefix=settings.api_v1_prefix)
app.include_router(policies.router, prefix=settings.api_v1_prefix)
app.include_router(compilation.router, prefix=settings.api_v1_prefix)
app.include_router(verification.router, prefix=settings.api_v1_prefix)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception handler caught: {exc}")
    
    if settings.debug:
        # In debug mode, return detailed error information
        import traceback
        return HTTPException(
            status_code=500,
            detail={
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc()
            }
        )
    else:
        # In production, return generic error message
        return HTTPException(
            status_code=500,
            detail="Internal server error"
        )

# Health check at root level
@app.get("/ping")
async def ping():
    """Simple ping endpoint for load balancers"""
    return {"status": "ok", "message": "pong"}

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    ) 