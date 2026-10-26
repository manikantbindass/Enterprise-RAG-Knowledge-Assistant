# Initial audit — 26 October 2026

Baseline: existing main cloned from manikantbindass/Enterprise-RAG-Knowledge-Assistant. No existing files were replaced before inspection.

## Architecture and evidence

The Next.js App Router interface uses a reducer persisted as `rag_app_v2` in localStorage. Documents and conversations never reach the backend. `formatAnswer` quotes browser BM25 matches; it does not call an LLM. The login page accepts any password, assigns admin, and writes a forgeable cookie. Header and sidebar trust a browser-stored profile. These are source-verified findings, not successful enterprise features.

Python directories contain API gateway, authentication, users, documents, processing, embeddings, vector retrieval, chat, audit and notification services. Shared SQLAlchemy models target PostgreSQL/pgvector. Useful extraction, chunking, RRF, provider and UI implementations exist and are retained. They do not establish that the composed system runs.

## Execution baseline

- `npm install`: fails ERESOLVE; Next 15.0.0 expects React 18 or a specific React 19 release candidate, while the package requests stable React 19.
- Python unit collection initially cannot run: pytest is not installed. Existing fixtures also require PostgreSQL, asyncpg, shared import-path setup and multiple service dependencies.
- Docker daemon is unavailable on this machine. Container execution cannot be verified.
- No Alembic migration configuration was found. Makefile references absent docker-compose.dev.yml and backend/tests rather than root tests.
- CI invokes a nonexistent frontend test command, an obsolete/incompatible lint setup, and suppresses security scan failures. CD assumes staging credentials and a functioning Kubernetes installation.

## Security and integration gaps

- Frontend-only login grants everyone admin; cookie existence is not authentication.
- Enterprise documents, credentials/settings and chat histories are persisted in localStorage.
- Tenant middleware decodes unverified JWT claims; all downstream use needs independent verification.
- Original compose contains development credentials, services without verified startup integration, broad port exposure and mismatched build contexts/shared imports.
- Embedding settings describe text-embedding-3-large as 1536-dimensional without explicit dimensions, whereas the schema fixes vectors at 1536. Index compatibility must be enforced.
- Simulated typewriter chat is disconnected from backend SSE. Browser relevance percentages are not confidence probabilities.
- No interoperability evidence for SSO/SCIM, MFA, RLS, malware scanning, signed URL expiry or cloud resilience.

## Refactor and priorities

Preserve the legacy services as reference rather than deploy them by default. Add a coherent local modular FastAPI runtime with server-owned SQLite persistence, password hashing, revocable opaque sessions, tenant-derived authorization, durable ingestion states, real parsers, lexical retrieval, optional server-configured LLM streaming, and honest extractive mode. Reuse Next.js, existing dependencies and design foundations for a responsive workspace.

## Measurable acceptance criteria

1. Registration/login rejects wrong credentials and forged cookies; logout revokes server sessions.
2. Two independent organizations cannot access each other's documents, chunks or conversations, including forged tenant headers.
3. Upload, background indexing, preview, retrieval, chat persistence and deletion work through real HTTP requests.
4. With no provider configured, the UI explicitly labels extractive search and never pretends it generated an AI answer.
5. Configured provider output is consumed as backend SSE with completion/error/cancellation paths.
6. Frontend typecheck, lint, production build and runtime API tests pass; remaining enterprise capabilities are explicitly recorded.
7. Source and documentation are pushed to the requested GitHub repository; local URLs are checked before delivery.
