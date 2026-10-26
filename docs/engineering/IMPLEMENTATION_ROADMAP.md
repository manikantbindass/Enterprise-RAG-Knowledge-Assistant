# Implementation roadmap

1. **Stabilization:** audit baseline, fix dependencies and scripts, define an honest supported runtime and repeatable local startup.
2. **Local full stack:** asynchronous SQLAlchemy/SQLite persistence, Argon2 passwords, revocable HttpOnly sessions, CSRF origin checks, organization scoping, document jobs and parsers, lexical retrieval, chat SSE, real analytics and audit records.
3. **Product workspace:** responsive glass design, document library/preview, persisted conversations, provider configuration status, accessible navigation, themes and administrative member controls.
4. **Verification and delivery:** tenant/session/upload/stream tests, browser smoke coverage, production build, CI, Docker configuration, operational documentation and GitHub update.
5. **Enterprise storage (outstanding):** PostgreSQL migrations and pgvector, versioned dense embeddings, hybrid RRF evaluation, S3 signed downloads, distributed queue leases, Redis limits, retention and malware scanning.
6. **Enterprise identity (outstanding):** verified Keycloak/OIDC PKCE federation, email verification/recovery delivery, MFA, invitations, groups and SCIM interoperability tests. Do not advertise these before verification.
7. **Advanced capabilities (outstanding):** tested Azure/Anthropic adapters, rerankers, bounded LangGraph workflows, one fully authenticated permission-synchronizing connector, budgets, billing, telemetry, cloud deployment and operational resilience testing.

Local single-process operation is a development foundation. It is not a verified enterprise deployment. Each phase must record evidence in PROGRESS.md; credentials or external infrastructure cannot be replaced with fabricated results.
