# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Jev (TypeSafe) fact extraction with per-fact confidence; gpt-6-luna reads a request only when Jev is unsure of a needed fact or of any fact behind an approval
- Trusted facts on verify (REST and MCP) and `trusted_only` variables that are never read from request text
- Injection and out-of-scope guards; a suspected injection cannot end in approval
- Setup check for permission rules that never restrict anything, with one repair pass
- Regenerated sample policies in `data/policies/`
- Minimal Streamlit UI and benchmark write-up (`bench/RESULTS.md`)

### Changed
- Z3 evaluates rules three ways over unknown facts: a deny rule that could fire asks for the fact instead of being skipped
- Only numeric range constraints are assumed; other constraints are checked like deny rules
- Policy generator writes limits and approvals as deny rules and gives rare exceptions a safe default
- Extraction runs at reasoning effort `none`; the GPT prompt no longer assumes unstated facts
- Compilations are stored as JSON; pickled blobs are never loaded
- Docker Compose builds the image from this repository

### Removed
- OpenAI proxy scripts, the old generator prompt copy, and manual LLM test scripts

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