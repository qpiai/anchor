# Security Policy

## Reporting Vulnerabilities

Please report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue for a security problem.

## Supported Versions

Only the latest release on `main` receives fixes.

## Deployment Notes

- The API has no built-in authentication and allows any CORS origin. Run it on a private network or behind an authenticating proxy; do not expose it to the internet as is.
- Text in a request can claim anything, including approvals. For decisions that matter, pass facts from a system of record in `facts`, and mark those variables `trusted_only` (see the README).
- Keep `JEV_INJECTION_HOLDS_APPROVAL` and `HYBRID_FAIL_CLOSED` on unless you have a reason to trade safety for availability.

## Security Measures

- **No secrets in repository**: All API keys and sensitive configuration are handled via environment variables
- **Environment-based configuration**: Use `.env` files for local development, never commit them
- **Input validation**: Request bodies are validated with Pydantic schemas
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