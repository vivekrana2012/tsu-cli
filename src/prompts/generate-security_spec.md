# Focus

This profile produces a **security overview document** covering
authentication, data handling, and the threat surface. Prioritize reading
auth/middleware code, crypto usage, access control logic, input validation,
dependency manifests, and configuration for secrets management, CORS, TLS,
and security headers.

# Output Sections

## 1. Security Overview

A concise summary (2-3 paragraphs) of the project's overall security posture:
authentication model, trust boundaries, and the most significant
security-relevant design decisions.

## 2. Authentication & Authorization

Describe the auth implementation in detail:

- Authentication mechanism (OAuth2, JWT, API keys, sessions, etc.)
- Token generation, storage, and expiration
- Authorization model (RBAC, ABAC, scopes, policies)
- Session management and logout handling

Include an ASCII/Unicode flow diagram of the auth flow:

```
[Client] ──▶ [Login] ──▶ [Validate] ──▶ [Issue Token] ──▶ [Protected Resource]
```

## 3. Data Handling & Secrets

Document how the project handles sensitive data:

| Data Type | Storage | Encryption | Access Control | Notes |
| --------- | ------- | ---------- | -------------- | ----- |
| User passwords | Database | bcrypt hash | Auth service only | ... |
| API tokens | Keychain | At rest | ... | ... |
| ...       | ...     | ...        | ...            | ...   |

Include: secrets management approach, environment variable handling, config
file security, and any hardcoded credentials found.

## 4. Input Validation & Injection Defence

Document how the project validates user input and prevents injection attacks:

| Input Surface | Validation | Sanitisation | Risk if Bypassed |
| ------------- | ---------- | ------------ | ---------------- |
| ...           | ...        | ...          | ...              |

Cover: SQL injection, XSS, command injection, path traversal, deserialization,
and any framework-provided protections.

## 5. Dependency Security

List dependencies with known security implications:

| Dependency | Version | Known Issues | Notes |
| ---------- | ------- | ------------ | ----- |
| ...        | ...     | ...          | ...   |

Note any outdated packages, packages with known CVEs, or packages that have
been deprecated.

## 6. Network & Transport Security

Document network security configuration:

- TLS/SSL configuration
- CORS policy
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Rate limiting and DDoS protections
- API gateway or reverse proxy configuration

If not applicable, state what is and isn't configured.

## 7. Threat Surface Summary

Summarise the key attack surfaces and potential vulnerabilities:

| Threat | Affected Component | Current Mitigation | Risk Level |
| ------ | ------------------ | ------------------ | ---------- |
| ...    | ...                | ...                | ...        |

Rate risk as Low / Medium / High based on what the code reveals.
