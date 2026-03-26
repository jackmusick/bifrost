# Bifrost Integrations

**Open-source automation platform for Integration Services** - Built to democratize best-in-class tooling before venture capital gets the chance to own something we're all incredibly passionate about.

[![License: AGPL](https://img.shields.io/badge/License-AGPL-green.svg)](https://opensource.org/licenses/agpl)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)

---

## Table of Contents

-   [What is Bifrost Integrations?](#what-is-bifrost-integrations)
-   [Key Features](#key-features)
-   [Quick Start](#quick-start)
-   [Documentation](#documentation)
-   [Contributing](#contributing)
-   [License](#license)

---

## What is Bifrost Integrations?

Bifrost Integrations is an open-source automation platform designed to democratize best-in-class tooling for the emerging Integration Services industry - **before venture capital gets the chance to own something we're all incredibly passionate about: solving problems with automation**.

Built by someone with nearly 20 years of MSP experience and a deep passion for scaling solutions for the industry and its customers, this platform addresses a fundamental gap in the market. Just as early PSA and RMM tools transformed Managed Services, the Integration Services industry needs purpose-built tooling that truly scales automation. Existing RPA platforms are great for rapid development and provide helpful abstractions like OAuth, storage, and monitoring, but **they cannot and will not keep pace with AI-powered development** and have always been constrained by limitations that traditional programming languages do not have.

Bifrost Integrations removes those limitations while preserving the light management layer that makes RPA tools valuable - abstracting OAuth workflows, monitoring, configuration, and secret management. It's architected with multi-tenancy at its core, enabling you to scale your Integration Services business without duplicating work across customers. **This is not another RPA tool trying to be everything to everyone**; it's a platform designed specifically to help you build scalable automation businesses without the vendor lock-in.

### What You Can Do with Bifrost Integrations

**Develop with Your Favorite Tools**

-   Use VS Code, Claude Code, and Git for version control
-   Build with Python and modern development workflows
-   Test locally before deploying to production

**Build Reusable Integrations**

-   Create integration modules for common platforms (NinjaOne, HaloPSA, Pax8, Microsoft CSP)
-   Abstract authentication, pagination, and API complexity
-   Share functionality across all your workflows

**Centralized Connection Management**

-   Automated OAuth refresh flows
-   Key/value configuration storage per organization
-   Secure secrets management

**Dynamic Forms and Workflows**

-   Create flexible forms for you and your customers
-   Build context-aware workflows that adapt based on organization and user
-   Generate form inputs programmatically from data providers

**Multi-Tenant Architecture**

-   Scope functionality globally or to specific organizations
-   Deliver value to customers without code duplication or redeployment
-   Complete data isolation between tenants

### Why Bifrost Integrations Exists

Traditional RPA tools lower the barrier to entry but fall short when you need the full power of a programming language, version control, modern development practices, and AI-assisted workflows. Meanwhile, no one is building a platform truly designed to scale automation in the way early PSA and RMM tools scaled Managed Services. In my opinion, these tools are all good at different things, but they lack the flexibility to deliver solutions for both you and your customers.

Bifrost Integrations bridges this gap by giving you the power and flexibility of code with the convenience of RPA-style abstractions - all in an open-source package that you control. **It's built to ensure the next chapter of Integration Services doesn't get ravaged by venture capitalists who prioritize extraction over value creation**.

### For the Non-Developer

With AI coding tools, proper instructions, a thriving community, and training, it's never been easier to build powerful automations. Traditional RPA tools still require you to understand programming primitives like loops, variables, and conditional logic - they had their own syntax you needed to learn. While Bifrost Integrations may require a slightly higher initial investment to get started, the combination of AI-assisted development and a platform that abstracts the dangerous complexities (authentication, secrets management, API security) means **the ceiling is dramatically higher**.

AI tools like Claude Code, GitHub Copilot, and GPT Codex can help you:

-   Write workflows from natural language descriptions
-   Debug errors and explain what code is doing
-   Suggest improvements and optimizations
-   Generate boilerplate code for common patterns

The platform handles the hard parts - OAuth flows, credential encryption, multi-tenant isolation, and API authentication - so you can focus on solving business problems. With the right guidance and AI assistance, you can build automations that would have required a full development team just a few years ago, **enabling limitless possibilities for your Integration Services business**.

---

## Key Features

-   **Multi-Tenant Architecture** - Complete data isolation per organization
-   **OAuth Management** - Automated token refresh and credential storage
-   **Secrets Management** - Encrypted secrets with Fernet encryption
-   **Dynamic Workflows** - Python-based with full language capabilities
-   **Reusable Integrations** - Build once, use across all customers
-   **AI-Assisted Development** - Built for modern AI coding workflows
-   **Version Control** - Git-based workflow management
-   **Hot Reload** - Workflows and forms reload automatically on file changes
-   **Self-Hostable** - Run anywhere with Docker Compose

---

## Quick Start

### Prerequisites

-   Docker and Docker Compose
-   Git

### Running with Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/jackmusick/bifrost-api.git
cd bifrost-api

# Run setup (creates .env with secure random secrets)
./setup.sh

# Start all services
docker compose up
```

This starts:
-   **Client** (React) - http://localhost:3000
-   **API** (FastAPI) - proxied through client
-   **PostgreSQL** - Database
-   **Redis** - Caching and sessions
-   **RabbitMQ** - Message queue for async workflows

**Access the Platform:**

-   **Client UI**: http://localhost:3000
-   **API Docs (Swagger)**: http://localhost:3000/api/docs
-   **API Docs (ReDoc)**: http://localhost:3000/api/redoc

---

## Local Development

### Docker (Recommended)

The full stack runs in Docker with hot reload enabled for both API and client:

```bash
# Start all services with hot reload
docker compose up

# Or run in background
docker compose up -d

# View logs
docker compose logs -f api
docker compose logs -f client
```

Changes to files in `api/src/`, `shared/`, and `client/src/` automatically reload.

**VS Code Debugging:**

```bash
# Start with debugger enabled (API waits for VS Code to attach)
ENABLE_DEBUG=true docker compose up
```

Then attach VS Code debugger to port 5678. The API will wait for the debugger before starting.

### Native

For native development, run infrastructure in Docker and applications locally:

```bash
# Start infrastructure only
docker compose up -d postgres redis rabbitmq

# Set up Python virtual environment
cd api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the API with hot reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start the client
cd client
npm install
npm run dev
```

### Running Tests

```bash
# Run all tests (starts dependencies in Docker)
./test.sh

# Run specific test file
./test.sh tests/integration/platform/test_sdk_from_workflow.py

# Run with coverage
./test.sh --coverage

# Run E2E tests
./test.sh --e2e
```

### CLI Authentication Storage

The `bifrost` CLI now prefers the Unix `pass` password store for cached device
flow credentials and only falls back to `~/.bifrost/credentials.json` when
`pass` is unavailable.

```bash
# Default behavior on Unix: prefer pass, fallback to file
bifrost login

# Force pass-backed storage
export BIFROST_CREDENTIALS_BACKEND=pass

# Override the pass entry name (default: bifrost/credentials)
export BIFROST_PASS_ENTRY=bifrost/credentials
```

If an older plaintext credentials file exists and `pass` is available, the CLI
will migrate the stored credentials into `pass` automatically on the next read.

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   FastAPI   │────▶│ PostgreSQL  │
│   (React)   │     │    (API)    │     │  (Database) │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              ┌─────────┐   ┌──────────┐
              │  Redis  │   │ RabbitMQ │
              │ (Cache) │   │ (Queue)  │
              └─────────┘   └──────────┘
```

-   **FastAPI** - Async Python API with automatic OpenAPI documentation
-   **PostgreSQL** - Primary data store with SQLAlchemy ORM
-   **Redis** - Session storage and caching
-   **RabbitMQ** - Async workflow execution queue
-   **React** - Modern frontend with TypeScript

---

## Documentation

For detailed documentation on architecture, development, deployment, and usage:

-   **API Documentation**: http://localhost:8000/docs (when running)
-   **Frontend Repository**: Included in `client/` directory

---

## Contributing

This is intended to be a community-driven project built to ensure the Integration Services industry has the tools it needs without vendor lock-in or extractive pricing. However for the time being, while I work out the kinks, contributions and issues will be closed. Stay tuned!

## License

This project is licensed under the AGPL License - see the [LICENSE](LICENSE) file for details.

**Why AGPL?** To ensure this platform remains open and available to everyone. If you modify and deploy Bifrost, you must share those modifications with the community. This prevents proprietary forks and ensures improvements benefit everyone.

---

## Why This Matters

In my opinion, the MSP industry is at a critical juncture. We've all watched as venture capital transformed software markets and tools we use and love (loved?) - not always for the better. I believe the next frontier for MSP is in the Integration Services industry where we focus on using the automation skills we've developed over the last couple of decades and build value for new and existing customers.

**This is our chance to own the tools we build our businesses on.**
