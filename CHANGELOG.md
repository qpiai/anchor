# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.06.01] - 2025-09-29

### Added
- MCP (Model Context Protocol) server for AI assistant integration with policy verification
- Support for STDIO and SSE transport modes for flexible integration options
- Docker Compose service for MCP server with independent operation capability (runs without backend service)

## [1.0.0] - 2025-09-12

### Added
- Initial open-source release of Anchor policy verification system
- AI-powered document-to-policy generation using OpenAI GPT models
- Z3 formal logic compilation and mathematical verification engine
- Interactive policy editor with variable management (mandatory/optional)
- Document upload support (PDF, DOCX, TXT)
- RESTful API with comprehensive endpoints for policy management
- Streamlit-based UI for policy editing and testing
- Docker containerization with PostgreSQL database
- Comprehensive test coverage for all major scenarios
- Support for complex policy rules and nested conditions
- Real-time policy verification with detailed explanations
- Variable extraction with smart defaults and type inference
- Policy compilation to Z3 solver constraints
- Clarifying questions system for missing mandatory variables

### Security
- Environment-based configuration for API keys and secrets
- No hardcoded credentials in codebase
- Secure database password handling
- Input validation and sanitization

### Technical Features
- FastAPI backend with automatic OpenAPI documentation
- PostgreSQL database with SQLAlchemy ORM
- Z3 theorem prover integration for formal verification
- Alembic database migrations
- Docker Compose multi-service orchestration
- Comprehensive error handling and logging
- Health check endpoints for monitoring