# AGENT.md — Persona Mesh AI

This file provides working instructions for AI coding agents contributing to **Persona Mesh AI**.

## 1. Project Overview

Persona Mesh AI is a modular, multi-agent platform for creating and managing configurable AI personas and coordinating research-first content workflows.

The platform is intended to support:

- Configurable personas with distinct roles, instructions, writing styles, and permitted capabilities.
- Multi-agent workflows such as research, drafting, fact-checking, editing, and review.
- Web research, source extraction, and evidence-aware content generation.
- Campaign and content lifecycle management.
- Authorized integrations with publishing platforms such as DEV.to, Medium, and other supported services.
- Human review and approval before consequential actions such as publishing.
- Persistent storage of personas, campaigns, drafts, workflow state, connected accounts, and execution history.
- Observability for model calls, agent runs, latency, errors, and cost.

The project is currently in its initial development stage. Prefer a small, understandable implementation over premature complexity.

## 2. Core Technology Choices

Use the following stack unless the project owner explicitly changes the decision:

| Area | Technology |
|---|---|
| Language | Python 3.12 |
| Project and dependency management | `uv` |
| API | FastAPI |
| Data validation and settings | Pydantic, pydantic-settings |
| Agent orchestration | LangGraph |
| Model-provider routing | LiteLLM |
| Web search | Tavily |
| Web extraction | Firecrawl |
| Tool interoperability | MCP Python SDK |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy 2.x, Alembic |
| PostgreSQL driver | asyncpg |
| Workflow checkpointing | LangGraph PostgreSQL checkpoint integration |
| Observability | Langfuse |
| Testing | pytest, pytest-asyncio, respx |
| Linting and formatting | Ruff |

Do not introduce another agent framework (for example CrewAI, Google ADK, OpenAI Agents SDK, or Pydantic AI) without a concrete requirement and an explicit architectural decision. Avoid overlapping frameworks that solve the same problem.

Optional technologies such as pgvector, Redis, a job queue, a dedicated RAG framework, local embedding models, or browser automation should be introduced only when a real use case requires them.

## 3. Repository Structure

Keep application code under `src/agentmesh/` (or the package directory already established in `pyproject.toml`). The product name is **Persona Mesh AI**; do not rename the Python import package or distribution without checking the existing project configuration and discussing the change.

Suggested structure:

```text
.
├── AGENT.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── README.md
├── .env.example
├── src/
│   └── agentmesh/
│       ├── __init__.py
│       ├── __main__.py
│       ├── api/
│       ├── core/
│       ├── agents/
│       ├── personas/
│       ├── services/
│       ├── integrations/
│       └── db/
├── tests/
└── docs/
```

Responsibilities:

- `api/`: HTTP routes, request/response schemas, and API dependencies.
- `core/`: application configuration, shared interfaces, errors, and orchestration support.
- `agents/`: focused agent implementations and their input/output contracts.
- `personas/`: persona definitions, validation, versioning, and resolution.
- `services/`: use cases and business workflows such as campaigns, research, drafting, and review.
- `integrations/`: external provider clients and platform-specific adapters.
- `db/`: database models, repositories, and persistence concerns.
- `tests/`: unit, integration, and workflow tests.
- `docs/`: architecture decisions, setup instructions, and operational documentation.

Do not create empty abstractions or directories just to match this layout. Add modules when they have a clear responsibility.

## 4. Development Workflow

### Environment

Use `uv` for Python version management, virtual environments, dependency installation, scripts, and lockfile management.

Common commands:

```bash
uv sync
uv run python -m agentmesh
uv run uvicorn agentmesh.api.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format .
uv tree
```

Add dependencies with:

```bash
uv add package-name
uv add --dev package-name
```

Do not use `sudo pip`, install project dependencies globally, or manually edit `uv.lock`. Change dependencies through `uv add` / `uv remove`, then commit the updated `pyproject.toml` and `uv.lock`.

Use the project's configured Python version. Do not change `.python-version` without a compatibility reason and verification.

### Before finishing a change

1. Inspect the existing code and conventions before editing.
2. Make the smallest coherent change that solves the task.
3. Add or update tests for changed behavior.
4. Run relevant tests.
5. Run `uv run ruff check .` and `uv run ruff format .`.
6. Review the diff for accidental changes, secrets, generated files, and unrelated formatting.
7. Report what changed, what was tested, and anything that remains incomplete.

Never claim a command or test passed unless it was actually run and its result was observed.

## 5. Architecture Principles

### Keep responsibilities separate

- FastAPI handles transport and request lifecycle; it should not contain agent business logic.
- LangGraph coordinates multi-step workflows and state transitions.
- Agents perform bounded tasks and expose typed inputs and outputs.
- Services implement product use cases and coordinate domain operations.
- Integrations encapsulate external APIs and provider-specific behavior.
- Repositories and database modules own persistence details.
- Pydantic models define clear boundaries between modules.

Avoid a single giant agent, a giant route handler, or a generic utility module containing unrelated logic.

### Use explicit workflow state

LangGraph workflows should use typed, documented state schemas. Keep state limited to information required by the workflow. Avoid passing entire database records, credentials, or large documents through every node.

Represent important workflow steps explicitly, including:

1. Request validation.
2. Planning and task decomposition.
3. Research and source collection.
4. Draft generation.
5. Evidence and quality review.
6. Human approval where required.
7. Authorized publishing.
8. Result recording.

Use bounded retries and explicit error handling. Avoid infinite agent loops and uncontrolled recursive delegation.

### Treat personas as data

A persona should be a validated, versioned configuration, not a separate hardcoded Python class for every identity.

A persona may define:

- Name and description.
- Intended role and audience.
- Tone, style, and language preferences.
- System instructions and task constraints.
- Allowed tools and capabilities.
- Model preferences or routing hints.
- Output requirements.
- Review requirements.

Separate persona instructions from authorization. A persona's prompt must never grant access to an account, secret, or tool. Enforce permissions in application code and integration services.

### Use typed contracts

Prefer Pydantic models for agent inputs, outputs, API payloads, configuration, and persisted structured data.

Do not rely on parsing arbitrary prose when a structured schema is practical. Validate model-generated output before passing it to another agent or persisting it.

### Provider independence

Keep model-provider calls behind a small application-owned interface or a clearly isolated provider module. LiteLLM may be used for routing, but do not spread provider-specific configuration throughout business logic.

Support model choice by task when useful (for example, a stronger model for research synthesis and a lower-cost model for classification). Record provider, model, latency, and token/cost metadata when available.

## 6. Research and Content Quality

Research outputs should preserve evidence, not just summaries.

Where applicable, store:

- Source URL.
- Page title.
- Retrieval timestamp.
- Publication date, if available.
- Relevant extracted text or excerpts.
- Claims supported by each source.
- Confidence or verification status.

Do not invent citations, URLs, quotes, publication dates, statistics, or source contents. Clearly distinguish verified facts, reasonable interpretation, and unverified claims.

A reviewer should check relevance, factual support, consistency, readability, audience fit, and compliance with the requested format. A model-generated confidence score is not proof that a claim is true.

Respect website terms, robots restrictions, API terms, rate limits, and copyright. Do not bypass paywalls, authentication, access controls, or platform restrictions.

## 7. Account Safety, Publishing, and Human Approval

Only integrate accounts that the user owns or is explicitly authorized to operate.

- Do not impersonate real people or organizations.
- Do not create fake identities, fake engagement, fabricated testimonials, or coordinated deceptive consensus.
- Do not publish misleading content designed to manipulate public opinion or target a person through deceptive multi-account activity.
- Do not treat a persona as a real human identity unless the product's use is transparent and authorized.
- Follow each platform's current API and automation rules.
- Keep platform-specific publishing logic in separate adapters.
- Never assume a platform supports automated publishing merely because it has an API.
- Require explicit human approval before publishing unless the product owner has deliberately configured a narrowly scoped, compliant automation policy.
- Show the final content, destination account, and target platform before approval.
- Record who approved an action, when it was approved, and the resulting platform response.

Publishing is a consequential external action. Do not trigger it as a side effect of drafting, reviewing, or running a research workflow.

## 8. Security and Secrets

- Never commit API keys, passwords, access tokens, private keys, or real `.env` files.
- Read secrets from environment variables or an approved secrets manager.
- Maintain `.env.example` with placeholder values only.
- Do not log secrets, authorization headers, full tokens, or sensitive account data.
- Apply least-privilege permissions to tools and connected accounts.
- Validate and authorize every tool invocation on the server side.
- Treat web pages, retrieved documents, MCP responses, and user-provided content as untrusted data.
- Defend against prompt injection: retrieved content must not be allowed to override system instructions, grant permissions, or trigger unauthorized actions.
- Do not execute arbitrary code, shell commands, or browser actions based solely on model-generated text.
- Validate URLs and outbound destinations where server-side requests are made to reduce SSRF risk.

## 9. Database and Persistence

Use PostgreSQL for durable application data. Use SQLAlchemy for database access and Alembic for schema migrations.

Guidelines:

- Keep database models separate from API response schemas.
- Use migrations for schema changes; do not rely on automatic table creation in production.
- Use transactions for multi-step writes that must remain consistent.
- Add indexes based on query patterns, not speculation.
- Store timestamps in UTC and convert for display at the application boundary.
- Keep workflow checkpoints distinct from domain records such as campaigns, drafts, and personas.
- Do not store plaintext credentials in ordinary application tables.
- Add vector search (for example, pgvector) only when semantic retrieval is implemented and measured.

## 10. API Design

- Use clear resource-oriented endpoints.
- Validate request bodies and query parameters with Pydantic.
- Return consistent response shapes and appropriate HTTP status codes.
- Use dependency injection for database sessions and authenticated user context.
- Keep blocking I/O out of async request handlers.
- Add pagination to collection endpoints.
- Avoid exposing internal prompts, secrets, stack traces, or unrestricted workflow state.
- Document endpoints through FastAPI's OpenAPI support.

## 11. Testing and Evaluation

Use multiple test layers:

- Unit tests for pure logic, validation, persona resolution, and permissions.
- Integration tests for database repositories and external adapters.
- Workflow tests for LangGraph state transitions and failure paths.
- API tests for HTTP behavior and authorization.
- Evaluation datasets for research relevance, source support, persona consistency, and content quality.

Mock external model and platform calls in ordinary automated tests. Tests should not require paid API calls by default.

Include tests for:

- Invalid or incomplete model output.
- Search and extraction failures.
- Timeouts and retry limits.
- Duplicate workflow execution.
- Unauthorized tool access.
- Approval required before publishing.
- Publishing adapter errors and partial failures.
- Prompt-injection attempts in retrieved content.

Use deterministic assertions wherever possible. LLM-as-judge evaluations should supplement, not replace, ordinary tests and evidence checks.

## 12. Observability and Cost Control

Use Langfuse or the configured tracing system to record useful execution metadata.

Track:

- Workflow and node identifiers.
- Agent and persona identifiers.
- Provider and model.
- Duration and retry count.
- Token usage and estimated cost when available.
- Tool calls and outcomes.
- Validation failures.
- Approval and publishing outcomes.

Do not record secrets or unnecessary personal data. Set reasonable timeouts, token limits, concurrency limits, and retry budgets. Avoid unbounded loops and repeated calls that can create unexpected costs.

## 13. Code Style

- Use type hints for public functions and important internal interfaces.
- Prefer small functions with explicit inputs and outputs.
- Use `async` only when the operation is genuinely asynchronous.
- Use descriptive names; avoid cryptic abbreviations.
- Keep configuration out of source code.
- Use structured logging rather than `print()` in application code.
- Raise domain-specific exceptions where they improve error handling.
- Avoid premature abstractions and unnecessary design patterns.
- Add comments to explain non-obvious decisions, not to restate code.
- Follow Ruff formatting and lint rules configured by the repository.

## 14. Dependency Policy

Before adding a package:

1. Confirm that the feature is required now.
2. Check whether an existing dependency already provides the capability.
3. Prefer official SDKs and actively maintained packages.
4. Check Python compatibility, license, security posture, maintenance activity, and transitive dependencies.
5. Add only the required package and extras.
6. Update tests and documentation where behavior changes.

Do not install multiple competing agent frameworks, RAG frameworks, queues, or observability platforms without a documented reason. Resolve dependencies with `uv` and commit the lockfile.

## 15. Current Product Milestone

Build a small end-to-end workflow before expanding the platform.

Initial milestone:

1. Define a persona schema and store persona configurations.
2. Create three bounded roles: Researcher, Writer, and Reviewer.
3. Build a LangGraph workflow that passes validated outputs between those roles.
4. Use web research tools and preserve source metadata.
5. Generate a platform-neutral content draft.
6. Review the draft for factual support and persona consistency.
7. Require human approval; do not publish automatically.
8. Persist workflow results and trace execution.
9. Add tests for successful execution and common failure cases.

Do not build a large marketplace of personas, a complex multi-tenant permission system, multiple publishing adapters, or a sophisticated memory system before this core workflow works reliably.

## 16. Instructions for Coding Agents

When asked to implement a feature:

- First inspect the relevant files, project configuration, and tests.
- Follow existing naming, package, and architectural conventions.
- Explain any important architectural trade-off briefly.
- Do not rewrite unrelated modules or replace the chosen stack without permission.
- Do not invent API capabilities, credentials, environment variables, or platform behavior.
- If an external API's current behavior matters, verify it against current official documentation.
- If a requirement is ambiguous and affects data loss, security, account access, or publishing, ask before proceeding.
- Never perform destructive database, filesystem, Git, or external-account actions without explicit authorization.
- Provide a concise completion summary with changed files, tests run, and known limitations.

**Guiding principle:** Build Persona Mesh AI as a reliable, observable, secure workflow platform—not as an uncontrolled collection of autonomous agents.