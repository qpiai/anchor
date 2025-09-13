# Contributing to Anchor

Thank you for your interest in contributing to Anchor! We welcome contributions from the community and are grateful for any help you can provide.

## How to Contribute

### Reporting Issues
- Use the GitHub issue tracker to report bugs or request features
- Provide a clear description of the issue or feature request
- Include steps to reproduce bugs when applicable
- Add relevant labels to help categorize the issue

### Contributing Code

#### Getting Started
1. Fork the repository
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/automated_reasoning_check.git
   cd automated_reasoning_check
   ```
3. Set up your development environment:
   ```bash
   # Create virtual environment
   python -m venv test_env
   source test_env/bin/activate  # On Windows: test_env\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Set up environment variables
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

#### Development Workflow
1. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes following our coding standards
3. Test your changes thoroughly
4. Commit your changes with a clear commit message
5. Push to your fork and submit a pull request

#### Running Tests
```bash
# Run the complete system test
python tests/test_complete_system.py

# Test specific components
python tests/test_mandatory_variables.py
python tests/test_policy_editing.py

# Start the application for manual testing
python -m uvicorn app.main:app --host 0.0.0.0 --port 9066 --reload
```

#### Code Standards
- Follow PEP 8 Python style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise
- Handle errors appropriately with proper exception handling

#### Pull Request Guidelines
- Provide a clear description of what your PR does
- Reference any related issues
- Include tests for new functionality
- Ensure all existing tests pass
- Update documentation if necessary
- Keep PRs focused - one feature or bug fix per PR

### Documentation
- Update the README.md if you're adding new features
- Add docstrings to new functions and classes
- Update API documentation for new endpoints
- Include examples in your documentation

## Development Setup

### Docker Development
```bash
# Build and run with Docker
docker build --network=host -t anchor-backend .
docker-compose up -d

# View logs
docker-compose logs app
```

### Local Development
```bash
# Start PostgreSQL (if not using Docker)
# Configure DATABASE_URL in .env

# Start OpenAI proxy (if needed)
python openai_proxy.py

# Run the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 9066 --reload
```

## Project Structure

Understanding the codebase:

- `app/` - Main FastAPI application
  - `api/` - REST API endpoints
  - `services/` - Core business logic
  - `models/` - Database and Pydantic models
  - `core/` - Configuration and database setup
- `streamlit_ui/` - Interactive user interface
- `tests/` - Test files and debugging scripts
- `uploads/` - Document storage (gitignored)

## Security Guidelines

- Never commit API keys or sensitive information
- Use environment variables for all configuration
- Test with the provided `.env.example` template
- Follow the security guidelines in `SECURITY.md`

## Need Help?

- Check existing issues and documentation first
- Open an issue for questions or discussions
- Be respectful and constructive in all interactions

## License

By contributing to Anchor, you agree that your contributions will be licensed under the MIT License.