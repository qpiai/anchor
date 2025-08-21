import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from ..core.database import Base

class PolicyStatus(PyEnum):
    DRAFT = "draft"
    COMPILED = "compiled"
    ACTIVE = "active"

class CompilationStatus(PyEnum):
    SUCCESS = "success"
    ERROR = "error"

class VerificationResult(PyEnum):
    VALID = "valid"
    INVALID = "invalid"
    ERROR = "error"
    NEEDS_CLARIFICATION = "needs_clarification"

class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    domain = Column(String, nullable=False)  # hr, legal, finance, etc.
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    policies = relationship("Policy", back_populates="document")

class Policy(Base):
    __tablename__ = "policies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("policy_documents.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    domain = Column(String, nullable=False)
    version = Column(String, default="1.0")
    status = Column(Enum(PolicyStatus), default=PolicyStatus.DRAFT)
    
    # Policy content (JSON fields)
    variables = Column(JSON)  # Policy variables with types
    rules = Column(JSON)      # Policy rules and conditions
    constraints = Column(JSON)  # Global constraints
    examples = Column(JSON)   # Test scenarios
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = relationship("PolicyDocument", back_populates="policies")
    compilations = relationship("PolicyCompilation", back_populates="policy")
    verifications = relationship("Verification", back_populates="policy")

class PolicyCompilation(Base):
    __tablename__ = "policy_compilations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id"))
    z3_constraints = Column(Text)  # Serialized Z3 constraints
    compilation_status = Column(Enum(CompilationStatus))
    compilation_errors = Column(JSON)
    compiled_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    policy = relationship("Policy", back_populates="compilations")

class Verification(Base):
    __tablename__ = "verifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    extracted_variables = Column(JSON)
    verification_result = Column(String)  # Temporary: Use String instead of Enum to avoid PostgreSQL enum issues
    explanation = Column(Text)
    suggestions = Column(JSON)
    verified_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    policy = relationship("Policy", back_populates="verifications") 