# Lumina · Enterprise RAG Knowledge Assistant

An existing Next.js/FastAPI project rebuilt around a working, server-backed local knowledge workspace. Upload documents, search source passages, hold persistent conversations, and inspect citations in a responsive dark/light interface.

**Status:** verified local foundation in progress, not a completed enterprise platform. See [implementation progress](docs/engineering/PROGRESS.md), [initial audit](docs/engineering/INITIAL_AUDIT.md) and [roadmap](docs/engineering/IMPLEMENTATION_ROADMAP.md).

## Run locally on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/runtime/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Open [the application](http://localhost:3000) and **create a workspace**. Login requires a real registered account and a password of at least 12 characters. There are no default credentials. API documentation: [localhost:8000/docs](http://localhost:8000/docs).

The launcher writes hidden process IDs and logs under `data/logs`. Pass `-Development` for frontend hot reload. Data persists under `data/` and is excluded from Git. Full instructions for Windows, Linux/macOS, model configuration, backups and limitations are in [Operations](docs/engineering/OPERATIONS.md).

## Implemented local functionality

- Argon2 password hashing, expiring HttpOnly opaque sessions, logout revocation and Origin validation.
- Organization-scoped document access and search, author-private conversations, admin/member/viewer roles and account deactivation.
- Validated PDF, DOCX, XLSX and UTF-8 text uploads; real background extraction, bounded overlapping chunks, failure states, reindexing, previews and authenticated downloads.
- Server-side lexical BM25 retrieval with actual excerpts and PDF page references.
- Backend SSE events, persisted final answers, errors and cancellation; optional server-configured OpenAI and Ollama generation adapters.
- Real document/query/storage/member metrics, query chart and audit records.
- Responsive workspace navigation, document filters, conversation history/search/rename/delete/export, Markdown, clickable citation evidence and dark/light/system appearance.
- Isolated backend integration tests, frontend SSE parser tests, Playwright browser workflow, CI and local Docker configuration.

Without a configured model, answers explicitly show **retrieved excerpts, not generated AI**. Dense semantic search, pgvector hybrid retrieval and provider cost estimates are not part of the supported local runtime.

## Enable a model

Set environment variables on the **API server**, then restart it. Never enter provider credentials into browser storage.

```powershell
# Ollama: install and run a model first.
$env:RAG_PROVIDER='ollama'
$env:RAG_MODEL='<your-installed-model>'
$env:OLLAMA_BASE_URL='http://127.0.0.1:11434'
# Or: RAG_PROVIDER=openai, RAG_MODEL=<available-compatible-model>, OPENAI_API_KEY=<server-secret>
```

No model is downloaded or paid API call made automatically. Configuration failures are surfaced as errors. Provider orchestration tests use deterministic test streams; live provider verification requires a configured service.

## Docker

```bash
docker compose up --build
```

The default compose describes the supported API and frontend with a persistent local volume, bound to loopback. The original multi-service configuration is preserved as `docker-compose.legacy.yml` and is not a verified deployment. Docker image execution requires a running engine.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/runtime/tests -q --confcutdir=backend/runtime/tests
.\.venv\Scripts\python.exe -m ruff check backend/runtime
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
# With both servers running:
npx playwright install chromium
npm run test:e2e
```

## Architecture

```text
Browser → Next.js same-origin /api/v2 proxy → FastAPI modular runtime
                                             ├─ Argon2 + hashed opaque sessions
                                             ├─ Tenant-scoped SQLAlchemy / SQLite
                                             ├─ Persisted ingestion queue + parser worker
                                             ├─ BM25 source retrieval
                                             └─ Extractive SSE / configured LLM streaming
```

Legacy microservices, shared models and original architecture diagrams remain reference implementations. Current pages import `components/workspace` and `lib/runtime.ts`; they do not use the legacy browser-persisted stores or v1 clients. Existing browser records are preserved but not automatically migrated.

## Enterprise work remaining

PostgreSQL/Alembic/RLS, vector embeddings and hybrid RRF, S3 signed downloads, independent durable workers, distributed limits, document ACLs and versions, malware scanning/OCR, verified OIDC/SSO/MFA/recovery/SCIM, permission-synchronizing connectors, LangGraph workflows, budgets/billing, retention, production telemetry and deployment resilience require further implementation and verification. This local runtime must not be represented as SOC 2 certified or production-ready.
