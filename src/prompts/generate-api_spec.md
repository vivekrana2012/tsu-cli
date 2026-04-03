# Focus

This profile produces an **API specification document**. Prioritize reading
route/controller files, request/response models, middleware, and schema
definitions. Pay special attention to authentication mechanisms, error
response formats, rate limiting, and pagination patterns.

# Output Sections

## 1. API Overview

A concise summary (2-3 paragraphs) of the API: what it serves, its style
(REST, GraphQL, gRPC, etc.), base URL structure, and versioning approach.

## 2. Authentication & Authorization

Describe how the API authenticates requests (API keys, OAuth2, JWT, session
tokens, etc.). Include:

- Auth mechanism and flow
- Required headers or query parameters
- Token format and expiration (if applicable)
- Role-based or scope-based access control (if applicable)

## 3. Endpoints

List **every** endpoint found in the codebase in a table:

| Method | Path | Description | Auth Required |
| ------ | ---- | ----------- | ------------- |
| GET    | /api/v1/users | List all users | Yes |
| ...    | ...  | ...         | ...           |

Group endpoints by resource or domain area using subheadings if there are
many endpoints.

## 4. Request & Response Schemas

For each significant endpoint (or group of related endpoints), document:

- **Request body** — fields, types, required/optional, constraints
- **Response body** — fields, types, structure
- **Path/query parameters** — name, type, description

Use tables for structured representation:

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| ...   | ...  | ...      | ...         |

## 5. Error Handling

Document the API's error response format and common error codes:

| Status Code | Meaning | Response Body |
| ----------- | ------- | ------------- |
| 400         | Bad Request | `{"error": "..."}` |
| ...         | ...     | ...           |

## 6. Rate Limiting & Pagination

If applicable, document:

- Rate limit headers and thresholds
- Pagination strategy (cursor, offset, page-based)
- Pagination parameters and response metadata

If not applicable, state "No rate limiting or pagination detected."

## 7. Configuration

Document API-specific configuration: environment variables, feature flags,
or config files that affect API behaviour.

| Key / Option | Type | Default | Required | Description |
| ------------ | ---- | ------- | -------- | ----------- |
| ...          | ...  | ...     | ...      | ...         |
