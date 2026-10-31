# Persona Mesh AI 🧠

**A multi-agent AI platform for creating, managing, and orchestrating intelligent personas.**

Persona Mesh AI is an extensible AI platform designed to bring multiple specialized AI personas together to collaborate on complex tasks.

Instead of relying on a single general-purpose AI agent, Persona Mesh AI enables configurable personas with distinct roles, instructions, capabilities, and responsibilities. These personas can work together through structured workflows to research topics, generate content, validate information, review outputs, and coordinate publishing workflows.

The goal is to build a flexible ecosystem where AI personas can collaborate while maintaining individual identities, responsibilities, context, and permissions.

> **Project status:** Early development 🚧

---

## ✨ Vision

Imagine creating multiple AI personas, each with its own expertise, personality, writing style, and responsibilities.

For example:

- A **Researcher** that discovers information and gathers credible sources.
- A **Technical Writer** that transforms research into technical articles.
- A **Fact Checker** that validates claims and references.
- An **Editor** that improves readability, structure, and consistency.
- A **Content Strategist** that plans content around specific topics and audiences.

These personas can collaborate through an orchestrated workflow instead of operating as isolated AI assistants.

Persona Mesh AI aims to make this collaboration configurable, reusable, observable, and extensible.

## 🎯 Core Features

Planned capabilities include:

- **Persona Management:** Create, configure, update, and manage multiple AI personas.
- **Multi-Agent Orchestration:** Coordinate specialized agents using structured workflows.
- **Custom Instructions:** Define roles, objectives, writing styles, constraints, and behavioral guidelines.
- **AI Model Flexibility:** Connect different LLM providers and select models for different tasks.
- **Research Automation:** Search the web, extract information, and collect supporting references.
- **Content Generation:** Generate articles, technical posts, answers, and other content formats.
- **Content Review:** Validate generated content for factual accuracy, relevance, consistency, and quality.
- **Human-in-the-Loop:** Review and approve content before consequential actions.
- **Platform Integrations:** Connect authorized publishing accounts through supported platform APIs.
- **Persistent Memory:** Store relevant persona configurations, campaign information, and workflow history.
- **Observability:** Monitor agent executions, model usage, errors, latency, and costs.
- **Extensible Tooling:** Integrate external tools and services, including MCP-compatible servers.

*These are development goals, not a claim that every feature is currently implemented.*

## 🏗️ Architecture

The planned architecture separates the API, orchestration, agents, integrations, and persistence layers.

```text
                 PERSONA MESH AI
                        |
                        v
                  FastAPI Backend
                        |
                        v
                 Campaign Manager
                        |
                        v
                 LangGraph Runtime
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
      Researcher      Writer       Reviewer
          |             |             |
          v             v             v
      Web Search    LLM Provider   Validation
          |             |             |
          +-------------+-------------+
                        |
                        v
                Human Approval
                        |
                        v
              Publishing Integrations
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
        DEV.to        Medium       Other APIs
```

### Technology responsibilities

| Component | Responsibility |
|---|---|
| FastAPI | Backend API and request handling |
| LangGraph | Agent orchestration and workflow state |
| LiteLLM | Multi-provider model routing |
| Pydantic | Structured data and validation |
| Tavily | Web search and research |
| Firecrawl | Website crawling and content extraction |
| MCP | Standardized tool interoperability |
| PostgreSQL | Persistent application data |
| SQLAlchemy | Database access and ORM |
| Alembic | Database migrations |
| Langfuse | LLM observability and tracing |
| Pytest | Automated testing |
| Ruff | Code quality and formatting |

## 🛠️ Technology Stack

### Backend
- Python 3.12
- FastAPI
- Uvicorn
- Pydantic
- Pydantic Settings

### AI and Agentic Systems
- LangGraph
- LangChain (where required)
- LiteLLM
- MCP Python SDK

### Research and Data Extraction
- Tavily
- Firecrawl
- HTTPX

### Database and Persistence
- PostgreSQL
- SQLAlchemy
- asyncpg
- Alembic
- LangGraph PostgreSQL Checkpointer

### Observability
- Langfuse

### Development and Testing
- uv
- Pytest
- pytest-asyncio
- Ruff
- Git

## 📁 Project Structure

The initial project structure is organized by responsibility.

```text
persona-mesh-ai/
│
├── AGENT.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── .gitignore
│
├── src/
│   └── agentmesh/
│       ├── __init__.py
│       ├── __main__.py
│       │
│       ├── api/
│       │   └── __init__.py
│       │
│       ├── core/
│       │   └── __init__.py
│       │
│       ├── agents/
│       │   └── __init__.py
│       │
│       ├── personas/
│       │   └── __init__.py
│       │
│       ├── services/
│       │   └── __init__.py
│       │
│       ├── integrations/
│       │   └── __init__.py
│       │
│       └── db/
│           └── __init__.py
│
├── tests/
│
└── docs/
```

> The Python import package is currently named `agentmesh`, while the product is named Persona Mesh AI. These names can differ.

## 🚀 Getting Started

### Prerequisites

- Ubuntu Linux or another supported operating system
- Python 3.12
- uv
- Git
- PostgreSQL (when database functionality is introduced)

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd persona-mesh-ai
```

### 2. Install uv

If you don't already have uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reload your shell:

```bash
source "$HOME/.local/bin/env"
```

Verify:

```bash
uv --version
```

### 3. Install Python

```bash
uv python install 3.12
```

### 4. Install project dependencies

```bash
uv sync
```

This creates and synchronizes the project's virtual environment.

### 5. Configure environment variables

Create your local environment file:

```bash
cp .env.example .env
```

Add your API credentials when the corresponding integrations are implemented.

Example configuration:

```env
APP_NAME=Persona Mesh AI
APP_ENV=development
LOG_LEVEL=INFO

# AI Providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# Research
TAVILY_API_KEY=
FIRECRAWL_API_KEY=

# Database
DATABASE_URL=

# Observability
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
```

Only configure the credentials for services you actually use.

**Never commit your `.env` file or expose API credentials.**

### 6. Run the application

```bash
uv run python -m agentmesh
```

To start the development API server:

```bash
uv run uvicorn agentmesh.api.main:app --reload
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

## 📦 Dependency Management

Persona Mesh AI uses `uv` for Python dependency and environment management.

Common commands:

```bash
# Add a production dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Remove a dependency
uv remove package-name

# Synchronize dependencies
uv sync

# View dependency tree
uv tree

# Run Python
uv run python

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## 🧪 Testing

Run the test suite:

```bash
uv run pytest
```

Check code quality:

```bash
uv run ruff check .
```

Format the code:

```bash
uv run ruff format .
```

Testing will cover agent behavior, workflow transitions, structured outputs, integrations, authorization, and failure handling.

## 🗺️ Development Roadmap

The project will evolve incrementally.

- [ ] **Phase 1 — Foundation**
  - [x] Initialize Python project with uv
  - [x] Establish initial project structure
  - [ ] Configure application settings
  - [ ] Implement FastAPI foundation
  - [ ] Configure PostgreSQL
  - [ ] Establish logging and error handling

- [ ] **Phase 2 — Persona Engine**
  - [ ] Design persona schema
  - [ ] Implement persona creation and management
  - [ ] Support custom instructions and writing styles
  - [ ] Implement persona versioning
  - [ ] Define tool permissions and capabilities

- [ ] **Phase 3 — Agent Orchestration**
  - [ ] Integrate LangGraph
  - [ ] Create a common agent interface
  - [ ] Implement agent state management
  - [ ] Implement task delegation
  - [ ] Add retries and error handling
  - [ ] Add workflow persistence

- [ ] **Phase 4 — Research and Content Generation**
  - [ ] Integrate Tavily
  - [ ] Integrate Firecrawl
  - [ ] Build research workflows
  - [ ] Implement content generation
  - [ ] Implement fact-checking
  - [ ] Implement content review

- [ ] **Phase 5 — Memory and Knowledge**
  - [ ] Design persistent memory
  - [ ] Implement campaign context
  - [ ] Implement document ingestion
  - [ ] Add semantic retrieval
  - [ ] Evaluate vector search

- [ ] **Phase 6 — Integrations and Publishing**
  - [ ] Build platform adapter architecture
  - [ ] Integrate supported publishing APIs
  - [ ] Implement connected-account management
  - [ ] Implement approval workflows
  - [ ] Add publishing history
  - [ ] Implement scheduling

- [ ] **Phase 7 — Observability and Production**
  - [ ] Integrate Langfuse
  - [ ] Add agent evaluation datasets
  - [ ] Implement usage and cost tracking
  - [ ] Add security and permission audits
  - [ ] Optimize workflow performance
  - [ ] Prepare production deployment

## 🔐 Security and Responsible Automation

Persona Mesh AI is designed around authorized integrations and responsible AI automation.

- Only connect accounts you own or have permission to operate.
- Respect platform API policies, rate limits, and publishing restrictions.
- Keep credentials encrypted or in an appropriate secrets manager.
- Require human approval for publishing workflows by default.
- Preserve research references and avoid fabricated citations.
- Do not use personas for impersonation, fake engagement, or deceptive coordinated activity.
- Treat external content and retrieved documents as untrusted input.
- Enforce tool permissions independently of persona instructions.

## 🤝 Contributing

Contributions, ideas, bug reports, and architectural discussions are welcome.

Before submitting changes:

1. Review `AGENT.md` for project-specific development instructions.
2. Follow the existing architecture and coding conventions.
3. Add tests for new functionality.
4. Run the test suite and Ruff checks.
5. Document significant architectural decisions.

## 📄 License

The project's license has not yet been selected.

## 👨‍💻 Project

**Persona Mesh AI**

*A connected ecosystem of intelligent personas, working together.*

Built with curiosity, experimentation, and a passion for AI systems.
