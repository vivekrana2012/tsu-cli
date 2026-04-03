# Instructions

You are analyzing a software project in your current working directory.

1. Explore the project directory structure to understand the codebase layout.
2. Read key configuration files (package.json, pyproject.toml, Cargo.toml, pom.xml,
   go.mod, Gemfile, composer.json, etc.) to identify the tech stack.
3. Read source files to understand the architecture, patterns, and API surface.

# Output Sections

## 1. Overview

A concise summary (2-4 paragraphs) of what the project does, its purpose, and
key characteristics. Mention the primary language, framework, and deployment target
if identifiable.

## 2. Tech Stack & Frameworks

A table listing:

| Category       | Technology     | Version  | Notes          |
| -------------- | -------------- | -------- | -------------- |
| Language       | ...            | ...      | ...            |
| Framework      | ...            | ...      | ...            |
| Database       | ...            | ...      | ...            |
| ...            | ...            | ...      | ...            |

Include runtime, build tools, testing frameworks, and any notable libraries.

## 3. Architecture

Describe the high-level architecture: how modules/packages/services relate to
each other, key design patterns, data flow, and entry points.

**You MUST include the following visual representations using standard markdown:**

### 3a. Architecture Diagram

Use ASCII/Unicode box-and-arrow art to produce a component diagram showing the
main modules, services, or layers and their relationships. Example style:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│     API      │────▶│   Database   │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 3b. Flow Diagram

Use ASCII/Unicode flow notation to trace the primary data or request flow through
the system from entry point to output. Show branching logic and decision points
where meaningful. Example style:

```
[Input] ──▶ [Validate] ──▶ [Process] ──┬──▶ [Success Response]
                                        └──▶ [Error Response]
```

### 3c. Component Responsibilities

| Component / Module | Responsibility | Key Connections |
| ------------------ | -------------- | --------------- |
| ...                | ...            | ...             |

## 4. API Endpoints

If the project exposes REST or GraphQL endpoints, list them in a table:

| Method | Path            | Description          |
| ------ | --------------- | -------------------- |
| GET    | /api/v1/users   | List all users       |
| ...    | ...             | ...                  |

If no API endpoints are found, state "No API endpoints detected" and skip the table.

## 5. Configuration

Document all significant configuration the project exposes — environment variables,
config files, feature flags, CLI options, etc.

For each configuration source, produce a table:

| Key / Option       | Type     | Default  | Required | Description                     |
| ------------------ | -------- | -------- | -------- | ------------------------------- |
| `DATABASE_URL`     | string   | —        | Yes      | PostgreSQL connection string    |
| `PORT`             | number   | `3000`   | No       | HTTP server listen port         |
| ...                | ...      | ...      | ...      | ...                             |

If multiple config sources exist (e.g., `.env`, `config.yaml`, CLI flags), use a
separate table for each with a heading identifying the source.

If no configuration is found, state "No configurable options detected."

## 6. Dependencies Summary

List the key dependencies (not all, just the important ones) with their purpose:

| Dependency     | Version  | Purpose                        |
| -------------- | -------- | ------------------------------ |
| express        | ^4.18.0  | HTTP server framework          |
| ...            | ...      | ...                            |

Group by category (runtime, dev, build) if the list is long.

