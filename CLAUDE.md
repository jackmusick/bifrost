# Bifrost Integrations Platform

MSP automation platform built with FastAPI and React.

## Technologies

-   **Backend**: Python 3.11 (FastAPI), SQLAlchemy, Pydantic, PostgreSQL, RabbitMQ, Redis
-   **Frontend**: TypeScript 4.9+, React, Vite
-   **Storage**: PostgreSQL (data), Redis (cache/sessions), RabbitMQ (message queue)
-   **Infrastructure**: Docker, Docker Compose, GitHub Actions for CI/CD

## Development Environment (CRITICAL - READ FIRST)

### Everything Runs in Docker

**Development happens inside Docker containers, not on the host machine.**

Start the development stack:
```bash
./debug.sh  # Starts all services with hot reload enabled
```

This uses `docker-compose.dev.yml` and launches containers prefixed with `bifrost-dev-` or `bifrost-`:
- PostgreSQL, RabbitMQ, Redis, MinIO (infrastructure)
- API (internal port 8000, accessed via Vite proxy)
- Client (port 3000 - **this is your entry point**)
- Scheduler, Workers

**Access the app at http://localhost:3000** - Vite proxies API requests to the backend.

### Hot Reload is Automatic

All services have hot reload - **DO NOT restart containers for code changes**:
- **API**: Uvicorn watches `/app/src` and `/app/shared` - restarts automatically
- **Client**: Vite HMR - updates instantly in browser
- **Scheduler/Worker**: watchmedo monitors Python files - restarts automatically

### Vite Proxies All API Requests

The client at `localhost:3000` proxies `/api/*` to the API container. This means:
- Access the app at `http://localhost:3000` (not 8000)
- Type generation works from `client/` directory while stack is running
- No CORS issues - everything goes through Vite

### Container Management Rules

| Scenario | Correct Action | Wrong Action |
|----------|---------------|--------------|
| Code changes | Do nothing (hot reload) | Restart containers |
| New Python dependency | `docker compose restart api` | Rebuild everything |
| Database migration | `docker compose restart api` | Restart entire stack |
| Schema changes | Restart api, then `npm run generate:types` | Manual type updates |
| Something broken | Check logs first: `docker compose logs api` | Nuke and restart |

### DO NOT

- ❌ Run `docker compose up` if containers are already running
- ❌ Run pytest directly on host - use `./test.sh`
- ❌ Start a separate uvicorn/vite process outside Docker
- ❌ Restart the entire stack for single-service changes
- ❌ Manually write TypeScript types for API responses

## Project Structure

```
api/
├── src/              # FastAPI application
│   ├── handlers/     # HTTP endpoint handlers (thin layer)
│   ├── models/       # SQLAlchemy models
│   ├── jobs/         # Background job workers
│   └── main.py       # FastAPI app entry point
├── shared/           # Business logic, utilities
│   ├── models.py     # Pydantic models (source of truth)
│   └── ...
├── alembic/          # Database migrations
└── tests/            # Unit and integration tests

client/
├── src/
│   ├── services/     # API client wrappers
│   └── lib/
│       └── v1.d.ts   # Auto-generated TypeScript types
└── ...
```

## Project-Specific Rules

### Backend (Python/FastAPI)

-   **Models**: All Pydantic models MUST be defined in `api/shared/models.py`
-   **Routing**: Create one handler file per base route (e.g., `/discovery` → `discovery_handlers.py`)
    -   Sub-routes and related functions live in the same file
-   **Request/Response**: Always use Pydantic Request and Response models
-   **Business Logic**: MUST live in `api/shared/`, NOT in `api/src/handlers/`
    -   Handlers are thin HTTP handlers only
    -   Complex logic, algorithms, business rules go in shared modules
    -   Example: User provisioning logic lives in `shared/user_provisioning.py`

### Frontend (TypeScript/React)

-   **Type Generation**: Run `npm run generate:types` in `client/` after API changes
    -   Must run while API is running
    -   Types are auto-generated from OpenAPI spec based on `models.py`
    -   Never manually write TypeScript types for API endpoints
-   **API Services**: Create service files in `client/src/services/` for new endpoints

Example service pattern:
```typescript
import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type DataProvider = components["schemas"]["DataProviderMetadata"];
export type DataProviderResponse = components["schemas"]["DataProviderResponse"];

export async function getDataProviders() {
  return apiClient.get<DataProviderResponse>("/api/data-providers");
}
```

### Testing & Quality

-   **Tests**: All work requires unit and integration tests in `api/tests/`
    -   **IMPORTANT**: Always use `./test.sh` to run tests - it starts all required dependencies (PostgreSQL, RabbitMQ, Redis) in Docker
    -   Running pytest directly (`python -m pytest`) will FAIL for integration tests that need database access
    -   Run all tests: `./test.sh`
    -   Run specific test file: `./test.sh tests/integration/platform/test_sdk_from_workflow.py`
    -   Run specific test: `./test.sh tests/integration/platform/test_sdk_from_workflow.py::TestSDKFileOperations::test_file_path_sandboxing -v`
    -   Run with coverage: `./test.sh --coverage`
    -   Run E2E tests: `./test.sh --e2e`
-   **Type Checking**: Must pass `pyright` (API) and `npm run tsc` (client)
-   **Linting**: Must pass `ruff check` (API) and `npm run lint` (client)

### Commands

```bash
# Start Development (run from repo root)
./debug.sh                                # Start full stack with hot reload

# Testing (ALWAYS use test.sh - it manages Docker dependencies)
./test.sh                                 # Run all backend tests
./test.sh tests/unit/                     # Run unit tests only
./test.sh tests/integration/              # Run integration tests
./test.sh tests/integration/platform/test_sdk.py  # Run specific file
./test.sh --e2e                           # Run E2E tests (API + workers)
./test.sh --client                        # Run backend + Playwright E2E tests
./test.sh --client-dev                    # Fast Playwright iteration (keeps stack)
./test.sh --coverage                      # Run with coverage report

# Type Generation (requires dev stack running via ./debug.sh)
cd client && npm run generate:types       # Regenerate TypeScript types from API

# Individual Container Operations (uses docker-compose.dev.yml via ./debug.sh)
# If ./debug.sh is running, use these commands:
docker compose -f docker-compose.dev.yml restart api      # Restart API
docker compose -f docker-compose.dev.yml logs -f api      # Follow API logs
docker compose -f docker-compose.dev.yml logs -f worker   # Follow worker logs
# Or check container status:
docker ps --filter "name=bifrost"                         # List running containers

# Quality Checks
cd api && pyright                         # Type check Python
cd api && ruff check .                    # Lint Python
cd client && npm run tsc                  # Type check TypeScript
cd client && npm run lint                 # Lint TypeScript
```

### Common Workflows

**After adding/modifying Pydantic models:**
1. Make changes to `api/shared/models.py`
2. Hot reload updates API automatically
3. Run `cd client && npm run generate:types`
4. TypeScript types updated in `client/src/lib/v1.d.ts`

**After creating a new migration:**
1. Create migration: `cd api && alembic revision -m "description"`
2. Edit the migration file
3. Restart API to apply: `docker compose restart api`
4. Migration runs automatically on container start

**After adding a Python dependency:**
1. Add to `api/requirements.txt`
2. Rebuild and restart: `docker compose -f docker-compose.dev.yml up --build api`

## Pre-Completion Verification (REQUIRED)

Before marking any significant work complete, run this verification sequence:

```bash
# 1. Ensure dev stack is running
docker ps --filter "name=bifrost" | grep -q "bifrost-dev-api" || ./debug.sh

# 2. Backend checks (from api/ directory)
cd api
pyright                    # Type checking - must pass with 0 errors
ruff check .               # Linting - must pass

# 3. Regenerate frontend types (from client/ directory)
cd ../client
npm run generate:types     # Requires API to be running at localhost:3000

# 4. Frontend checks
npm run tsc                # Type checking - must pass
npm run lint               # Linting - must pass

# 5. Run tests
cd ..
./test.sh                  # All tests must pass
```

**This is mandatory for any changes that touch:**
- Backend API endpoints or models
- Frontend components or hooks
- Database schema or migrations
