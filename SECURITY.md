# Security Policy

## Reporting Vulnerabilities

If you discover a vulnerability in this library, please report it by opening a GitHub issue.

For sensitive security issues, please contact the maintainers directly instead of opening a public issue.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅        |

## Security Measures

- **No secrets in repository**: All API keys and sensitive configuration are handled via environment variables
- **Environment-based configuration**: Use `.env` files for local development, never commit them
- **Input validation**: All API endpoints validate and sanitize user inputs
- **Database security**: Parameterized queries prevent SQL injection
- **Dependencies**: Regular dependency updates to address known vulnerabilities
- **Container security**: Non-root user in Docker containers

## Best Practices for Users

1. **API Keys**: Never commit your OpenAI API keys or other secrets to version control
2. **Environment Files**: Copy `.env.example` to `.env` and configure your secrets there
3. **Database**: Use strong passwords for database connections
4. **Updates**: Keep dependencies updated to get security patches
5. **Network**: Run the service behind proper network security in production

## Security Features

- Environment variable configuration for all sensitive data
- Automatic input validation and sanitization
- Secure database connection handling
- Docker container security with non-root user
- No hardcoded credentials anywhere in the codebase