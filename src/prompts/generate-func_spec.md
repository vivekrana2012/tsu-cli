# Focus

This profile produces a **functional specification document** covering
business rules, workflows, and domain logic. Prioritize reading service
and use-case files, validation logic, data transformation pipelines, and
tests (especially integration/acceptance tests) to discover expected
behaviours and edge cases.

# Output Sections

## 1. Functional Overview

A concise summary (2-3 paragraphs) of what the system does from a business
perspective: the domain it operates in, key capabilities, and the primary
user workflows it supports.

## 2. Business Rules

List all business rules found in the codebase. For each rule, document:

| Rule ID | Description | Source File | Conditions | Action |
| ------- | ----------- | ----------- | ---------- | ------ |
| BR-001  | ...         | ...         | ...        | ...    |

Group rules by domain area using subheadings if there are many.

## 3. Workflows & Processes

For each key workflow or multi-step process, describe:

- **Trigger** — what starts the workflow
- **Steps** — ordered sequence of actions
- **Decision points** — conditions that branch the flow
- **Outcomes** — success and failure paths

Use ASCII/Unicode flow diagrams to illustrate complex workflows:

```
[Trigger] ──▶ [Step 1] ──▶ [Decision] ──┬──▶ [Path A]
                                          └──▶ [Path B]
```

## 4. Validation Rules

Document all input validation, data constraints, and business invariants:

| Field / Entity | Validation | Error Behaviour |
| -------------- | ---------- | --------------- |
| ...            | ...        | ...             |

## 5. Data Transformations & Mappings

If the system transforms data between formats, systems, or models, document
the mappings:

| Source Field | Target Field | Transformation | Notes |
| ------------ | ------------ | -------------- | ----- |
| ...          | ...          | ...            | ...   |

If no transformations are found, state "No data transformations detected."

## 6. Domain Model

Describe the key domain entities, their relationships, and important
attributes:

| Entity | Key Attributes | Relationships |
| ------ | -------------- | ------------- |
| ...    | ...            | ...           |

Include an ASCII/Unicode diagram showing entity relationships if there are
more than a few entities.

## 7. Edge Cases & Special Handling

Document any special cases, exceptions, or non-obvious behaviours found in
the code — boundary conditions, fallback logic, retry strategies, etc.
