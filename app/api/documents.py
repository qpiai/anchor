from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import uuid

from ..core.database import get_db
from ..models.database import PolicyDocument, Policy
from ..models.schemas import DocumentUploadResponse, PolicyDocumentResponse, ErrorResponse
from ..services.document_processor import DocumentProcessor
from ..services.policy_generator import PolicyGeneratorService

router = APIRouter(prefix="/documents", tags=["documents"])

# Initialize services
document_processor = DocumentProcessor()
policy_generator = PolicyGeneratorService()

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    domain: str = Form(...),
    db: Session = Depends(get_db)
):
    """Upload and process a policy document"""
    
    try:
        # Process the uploaded file
        file_data = await document_processor.process_uploaded_file(file, domain)
        
        # Create document record in database
        document = PolicyDocument(
            filename=file_data['filename'],
            content=file_data['content'],
            domain=domain
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Trigger background policy generation
        background_tasks.add_task(
            generate_policy_background,
            document.id,
            file_data['content'],
            domain,
            db
        )
        
        return DocumentUploadResponse(
            document_id=document.id,
            filename=file_data['filename'],
            status="uploaded"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/{document_id}", response_model=PolicyDocumentResponse)
async def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get document details by ID"""
    
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@router.get("/", response_model=List[PolicyDocumentResponse])
async def list_documents(
    domain: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List all documents with optional domain filtering"""
    
    query = db.query(PolicyDocument)
    
    if domain:
        query = query.filter(PolicyDocument.domain == domain)
    
    documents = query.offset(offset).limit(limit).all()
    
    return documents

@router.delete("/{document_id}")
async def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a document and all associated policies"""
    
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete associated policies first
    db.query(Policy).filter(Policy.document_id == document_id).delete()
    
    # Delete the document
    db.delete(document)
    db.commit()
    
    return {"message": "Document deleted successfully"}

async def generate_policy_background(document_id: uuid.UUID, content: str, domain: str, db: Session):
    """Background task to generate policy from document"""
    
    try:
        # Generate policy using LLM
        policy_data = await policy_generator.generate_policy_from_document(content, domain)
        
        # Create policy record
        policy = Policy(
            document_id=document_id,
            name=policy_data.get('policy_name', 'Generated Policy'),
            description=policy_data.get('description', ''),
            domain=domain,
            version=policy_data.get('version', '1.0'),
            variables=policy_data.get('variables', []),
            rules=policy_data.get('rules', []),
            constraints=policy_data.get('constraints', []),
            examples=policy_data.get('examples', [])
        )
        
        db.add(policy)
        db.commit()
        
        print(f"Policy generated successfully for document {document_id}")
        
    except Exception as e:
        print(f"Policy generation failed for document {document_id}: {str(e)}")

@router.get("/{document_id}/policies", response_model=List)
async def get_document_policies(document_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get all policies generated from a specific document"""
    
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    policies = db.query(Policy).filter(Policy.document_id == document_id).all()
    
    return policies 