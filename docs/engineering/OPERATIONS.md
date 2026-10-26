# Supported runtime and operating boundaries

The default stack is a modular FastAPI application (`backend/runtime`) and Next.js. Original microservice source and `docker-compose.legacy.yml` are preserved for reference. They are not the supported deployment path and have not passed the new runtime checks.

## Local startup (Windows)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/runtime/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Use `-Development` for Next.js development mode. The launcher starts hidden processes and records their PIDs and logs under `data/logs`. It refuses to take over occupied ports. Stop only the processes recorded by your run after checking their identities. API: http://localhost:8000/docs; frontend: http://localhost:3000.

If port 3000 is occupied, pass `-FrontendPort 3100`; the launcher also configures the API's allowed origins for that port. Do not rebuild `.next` while the production frontend is serving requests; stop that frontend process, build, then restart it. The supported standalone launcher copies the static assets into the standalone server directory.

On Linux/macOS, create a Python 3.12 virtual environment, install the same requirements, and run `uvicorn backend.runtime.main:app --host 127.0.0.1 --port 8000` from the root and `npm run start` from frontend in separate terminals.

Create your own account at `/register`. There is no shared default password. Registration creates an independent organization. Administrators can add members and viewers in Administration. Passwords require at least 12 characters and are hashed with Argon2. Sessions are random opaque tokens, stored as hashes in the database, expiring after eight hours; logout, role changes and deactivation revoke sessions.

## Model configuration

The default `RAG_PROVIDER=extractive` runs real BM25 retrieval and returns exact source excerpts. This is not LLM generation, semantic retrieval or hybrid search. No fabricated tokens, costs, progress percentages or confidence probabilities are displayed.

For a local model, run Ollama and pull a model supported by your installation, then export the following **before starting the API**:

```powershell
$env:RAG_PROVIDER='ollama'
$env:RAG_MODEL='<your-installed-model>'
$env:OLLAMA_BASE_URL='http://127.0.0.1:11434'
```

For OpenAI, set `RAG_PROVIDER=openai`, `RAG_MODEL` to a Chat Completions-compatible model available to your account, and `OPENAI_API_KEY` only in the server environment. Model availability is not assumed. Restart the API and reload the UI after configuration changes. Unavailable providers produce stream errors; the app never pretends a paid model is responding. OpenAI and Ollama adapters have deterministic stream orchestration tests; actual model calls require credentials or a running local model and are separately unverified until exercised.

`.env.local.example` documents settings; native uvicorn startup does not automatically load it. Docker Compose loads a root `.env`. Never commit that file. API_INTERNAL_URL configures the frontend proxy; Docker builds use `http://api:8000`.

The root `.env.example` now describes the supported runtime. Original microservice environment settings are retained in `.env.microservices.example` for reference. Python direct dependencies use a committed constraints lock; frontend installs use package-lock.json.

## Data and isolation

SQLite database and original files live in `data/`, excluded from Git. Back up that directory using SQLite's backup API or with the application stopped; include originals and database together. Organization identity is resolved through verified session membership, never an incoming tenant header. Organization documents are shared with active organization members; document-specific ACLs and workspace subdivisions are outstanding. Conversations are scoped to their author as well as organization. Viewer accounts can search and chat but cannot upload, delete or reindex.

Legacy browser storage is preserved without being imported or read by the new runtime. It may still contain sensitive records from the previous app. Export or remove those records yourself only after deciding what to preserve.

Document jobs are persisted as queued/extracting/chunking/indexed/failed records. Startup recovers interrupted jobs. One worker processes the queue within the API process. Run **one API process**; distributed leases and independent workers are outstanding. Original files are served as authenticated attachments, not signed public URLs. Text previews are inert React text; Markdown uses react-markdown without raw HTML support. PDF page numbers are real; DOCX and spreadsheets do not invent page references.

Deleting a document deletes its chunks and original file and removes source excerpts from future conversation reads. Historical answer text can still contain quotations; deletion is not a comprehensive retention or erasure policy. A request already streaming can retain its retrieved context. Do not claim strict permission revocation during an in-flight response.

## Upload boundaries

20 MB per upload, PDF magic validation, Office archive structure and 80 MB expansion cap, strict UTF-8 text, no null bytes, maximum 1000 PDF pages / 20,000 rows per sheet / 2 million extracted characters. Files are assigned server-generated storage IDs. Scanned PDFs fail with a clear OCR-required message. Legacy DOC/XLS, PPTX, image OCR, malware scanning and document versions are not supported by this runtime.

Parsing is offloaded to a thread and has size bounds, but is not sandboxed against hostile parser exploits. Before exposing uploads beyond a trusted local environment, isolate parsers, add process-level resource limits, a reverse-proxy body-size limit and malware scanning. FastAPI multipart parsing can buffer request data before the endpoint enforces its read limit.

## Deployment

`docker compose up --build` describes a two-container local stack bound to loopback. Configuration parsing is testable without a daemon; image builds and startup require Docker's engine. No cloud deployment or Kubernetes resilience is implied.

For internet-facing operation, complete the enterprise roadmap first: PostgreSQL/Alembic migrations and RLS tests, distributed jobs and Redis limits, object storage, robust retention, verified OIDC/MFA and recovery, operational telemetry and incident procedures. Enforce HTTPS, set `RAG_SECURE_COOKIES=true`, disable open self-registration and use exact `RAG_ALLOWED_ORIGINS`. API cookies use SameSite=Lax and all mutating requests require an allowed Origin; non-browser clients must send that Origin explicitly. CORS is unnecessary because the browser uses a same-origin Next.js proxy. The local CSP still allows inline/eval script execution required by the development setup; adopt nonce-based production CSP before external deployment.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend/runtime/tests -q --confcutdir=backend/runtime/tests
.\.venv\Scripts\python.exe -m ruff check backend/runtime
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
# Start both servers first, then:
npm run test:e2e
```

Frontend lint targets the supported application; legacy clients/stores remain source references and are not imported by current pages. Original tests require additional microservice dependencies and infrastructure; they are not counted as passing. Token counts, provider costs, document-level ACLs, SCIM, federation, advanced workflows and connectors remain unimplemented in this runtime. See IMPLEMENTATION_ROADMAP.md.

## Implementation references

Provider event formats were checked against [official OpenAI Chat Completions documentation](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [Ollama chat documentation](https://docs.ollama.com/api/chat). Next.js 15.5.28 matches the [official October 14 security update](https://nextjs.org/blog/nextjs-security-update-october-14-2026). Local stream tests use HTTPX mock transport; they do not establish account-specific model availability or live model quality.
