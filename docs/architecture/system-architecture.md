# Enterprise RAG Knowledge Assistant — System Architecture

## Overview

Multi-tenant, cloud-native RAG platform using a microservices architecture.

---

## High-Level System Architecture

```mermaid
graph TB
    subgraph CLIENTS["Clients"]
        Browser["🌐 Browser<br/>(Next.js 15)"]
        Mobile["📱 Mobile Apps"]
        APIConsumer["🔌 API Consumers"]
    end

    subgraph CDN["CDN / Load Balancer"]
        LB["⚖️ NGINX / ALB<br/>TLS Termination"]
    end

    subgraph GATEWAY["API Gateway Layer"]
        GW["🚦 API Gateway<br/>FastAPI<br/>Auth · Rate Limit · Routing"]
    end

    subgraph SERVICES["Microservices"]
        AUTH["🔐 Auth Service<br/>Keycloak · JWT · RBAC"]
        USER["👤 User Service<br/>Users · Orgs · Roles"]
        DOC["📄 Document Service<br/>Upload · S3 · Metadata"]
        PROC["⚙️ Processing Service<br/>OCR · Extract · Chunk"]
        EMB["🧮 Embedding Service<br/>OpenAI · BGE · Ollama"]
        VEC["🔍 Vector Service<br/>pgvector · Hybrid Search"]
        CHAT["💬 Chat Service<br/>LangGraph · RAG Pipeline"]
        AUDIT["📋 Audit Service<br/>Logs · Compliance"]
        NOTIF["🔔 Notification Service<br/>Email · Webhooks"]
    end

    subgraph QUEUE["Message Queue"]
        MQ["🐇 RabbitMQ<br/>Async Job Processing"]
    end

    subgraph DATA["Data Layer"]
        PG[("🐘 PostgreSQL 16<br/>+ pgvector")]
        REDIS[("⚡ Redis 7<br/>Cache · Sessions")]
        MINIO[("🗄️ MinIO / S3<br/>Document Storage")]
    end

    subgraph AI["AI / LLM Layer"]
        OPENAI["OpenAI<br/>GPT-4o · Embeddings"]
        ANTHROPIC["Anthropic<br/>Claude 3.5"]
        AZURE["Azure OpenAI<br/>Enterprise"]
        OLLAMA["🦙 Ollama<br/>Local LLM"]
    end

    subgraph OBS["Observability"]
        PROM["📊 Prometheus"]
        GRAF["📈 Grafana"]
        ELK["📝 ELK Stack"]
        OTEL["🔭 OpenTelemetry"]
    end

    Browser --> LB
    Mobile --> LB
    APIConsumer --> LB
    LB --> GW
    GW --> AUTH
    GW --> USER
    GW --> DOC
    GW --> CHAT
    GW --> AUDIT

    DOC --> MQ
    MQ --> PROC
    PROC --> MQ
    MQ --> EMB
    EMB --> VEC

    CHAT --> VEC
    CHAT --> OPENAI
    CHAT --> ANTHROPIC
    CHAT --> AZURE
    CHAT --> OLLAMA

    AUTH --> REDIS
    USER --> PG
    DOC --> MINIO
    DOC --> PG
    PROC --> PG
    VEC --> PG
    CHAT --> PG
    AUDIT --> PG

    GW --> PROM
    SERVICES --> OTEL
    OTEL --> PROM
    PROM --> GRAF
    SERVICES --> ELK
```

---

## Document Ingestion Pipeline

```mermaid
flowchart LR
    A["📤 Upload"] --> B["🦠 Virus Scan\n(ClamAV)"]
    B --> C["📋 Validate\nType · Size"]
    C --> D["☁️ Store\nS3/MinIO"]
    D --> E["🔎 OCR\nTesseract/Azure DI"]
    E --> F["📝 Text\nExtraction"]
    F --> G["🧹 Clean &\nNormalize"]
    G --> H["✂️ Chunking\nStrategy"]
    H --> I["🧮 Generate\nEmbeddings"]
    I --> J["💾 Store\npgvector"]
    J --> K["✅ Index\nComplete"]

    style A fill:#4f46e5,color:#fff
    style K fill:#10b981,color:#fff
```

---

## RAG Query Pipeline

```mermaid
flowchart TB
    A["💬 User Query"] --> B["✏️ Query\nRewriting"]
    B --> C["🎯 Intent\nDetection"]
    C --> D{Intent Type}

    D -- "Search" --> E["🔍 Multi-Query\nRetriever"]
    D -- "Agentic" --> F["🤖 LangGraph\nAgent Router"]

    E --> G["📊 Hybrid Search\nSemantic + BM25"]
    G --> H["🔄 Re-ranking\nCross-Encoder"]

    F --> I["Research\nAgent"]
    F --> J["Policy\nAgent"]
    F --> K["Compliance\nAgent"]

    H --> L["📦 Context\nBuilder"]
    I --> L
    J --> L
    K --> L

    L --> M["🤖 LLM\nGPT-4o / Claude / Ollama"]
    M --> N["✅ Answer with\nSource Citations"]
    N --> O["💾 Store in\nConversation History"]

    style A fill:#4f46e5,color:#fff
    style N fill:#10b981,color:#fff
```

---

## Multi-Tenancy Architecture

```mermaid
graph TB
    subgraph ORGA["🏢 Organization A"]
        UA["Users A"]
        DA["Documents A"]
        VA["Vectors A"]
        CA["Conversations A"]
    end

    subgraph ORGB["🏢 Organization B"]
        UB["Users B"]
        DB["Documents B"]
        VB["Vectors B"]
        CB["Conversations B"]
    end

    subgraph ORGC["🏢 Organization C"]
        UC["Users C"]
        DC["Documents C"]
        VC["Vectors C"]
        CC["Conversations C"]
    end

    subgraph DB_LAYER["Database Layer — Row Level Security"]
        PG[("PostgreSQL\norg_id isolation\nRLS Policies")]
    end

    ORGA --> PG
    ORGB --> PG
    ORGC --> PG
```

---

## Authentication & RBAC Flow

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Gateway as API Gateway
    participant Keycloak
    participant Service as Microservice
    participant DB as PostgreSQL

    User->>Frontend: Login (email/password or SSO)
    Frontend->>Keycloak: OIDC Authorization Request
    Keycloak->>User: Login form / SSO redirect
    User->>Keycloak: Credentials
    Keycloak->>Frontend: Access Token + Refresh Token (JWT)
    Frontend->>Gateway: Request + Bearer Token
    Gateway->>Keycloak: Validate Token (JWKS)
    Keycloak->>Gateway: Token valid + Claims
    Gateway->>Gateway: Check RBAC permissions
    Gateway->>Service: Forwarded request + user context
    Service->>DB: Query with org_id filter (RLS)
    DB->>Service: Tenant-scoped data
    Service->>Frontend: Response
```

---

## Deployment Architecture (Kubernetes)

```mermaid
graph TB
    subgraph INTERNET["Internet"]
        USERS["Users"]
    end

    subgraph AWS["AWS / Cloud"]
        subgraph VPC["VPC"]
            subgraph PUBLIC["Public Subnets"]
                ALB["Application Load Balancer"]
                NAT["NAT Gateway"]
            end

            subgraph PRIVATE["Private Subnets (EKS)"]
                subgraph K8S["Kubernetes Cluster"]
                    subgraph NS_APP["Namespace: rag-app"]
                        FE["Frontend Pods\n(3 replicas)"]
                        GW["API Gateway\n(3 replicas)"]
                        AUTH["Auth Service\n(2 replicas)"]
                        CHAT["Chat Service\n(5 replicas)"]
                        PROC["Processing Workers\n(auto-scale)"]
                        EMB["Embedding Workers\n(auto-scale)"]
                    end

                    subgraph NS_DATA["Namespace: rag-data"]
                        PG["PostgreSQL\n(RDS Proxy)"]
                        REDIS["Redis\n(ElastiCache)"]
                        MQ["RabbitMQ\n(AmazonMQ)"]
                    end

                    subgraph NS_MON["Namespace: monitoring"]
                        PROM["Prometheus"]
                        GRAF["Grafana"]
                        ELK["ELK Stack"]
                    end
                end
            end

            subgraph MANAGED["Managed Services"]
                RDS["RDS PostgreSQL\n(Multi-AZ)"]
                CACHE["ElastiCache Redis\n(Cluster Mode)"]
                S3["S3 Buckets\n(Encrypted)"]
                SECRETS["Secrets Manager"]
            end
        end
    end

    USERS --> ALB
    ALB --> GW
    GW --> AUTH
    GW --> CHAT
    CHAT --> PG
    CHAT --> REDIS
    PROC --> MQ
    FE --> ALB
```

---

## Service Communication

```mermaid
graph LR
    subgraph SYNC["Synchronous (HTTP/gRPC)"]
        GW -->|REST| AUTH
        GW -->|REST| USER
        GW -->|REST| DOC
        GW -->|REST| CHAT
        GW -->|REST| AUDIT
        CHAT -->|REST| VEC
    end

    subgraph ASYNC["Asynchronous (RabbitMQ)"]
        DOC -->|doc.uploaded| PROC
        PROC -->|doc.processed| EMB
        EMB -->|embed.complete| VEC
        CHAT -->|audit.event| AUDIT
        PROC -->|notif.event| NOTIF
    end
```

---

## Data Flow Sequence — Document Upload to Query

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant GW as API Gateway
    participant DS as Document Service
    participant S3 as MinIO/S3
    participant MQ as RabbitMQ
    participant PS as Processing Service
    participant ES as Embedding Service
    participant VS as Vector Service
    participant PG as PostgreSQL

    Note over User, PG: INGESTION PHASE
    User->>FE: Upload document
    FE->>GW: POST /api/v1/documents/upload
    GW->>DS: Forward with auth context
    DS->>S3: Store raw file
    DS->>PG: Create document record (status=pending)
    DS->>MQ: Publish doc.uploaded event
    DS->>FE: Return document_id

    MQ->>PS: Consume doc.uploaded
    PS->>S3: Download file
    PS->>PS: OCR + Extract text
    PS->>PS: Clean + Chunk text
    PS->>PG: Store chunks (status=chunked)
    PS->>MQ: Publish doc.chunked event

    MQ->>ES: Consume doc.chunked
    ES->>ES: Generate embeddings (batch)
    ES->>PG: Store embeddings in pgvector
    ES->>PG: Update document (status=indexed)

    Note over User, PG: QUERY PHASE
    User->>FE: Ask question
    FE->>GW: POST /api/v1/chat/messages
    GW->>CS: Forward to Chat Service
    CS->>CS: Rewrite query
    CS->>VS: Hybrid search (semantic + BM25)
    VS->>PG: Vector similarity + full-text search
    PG->>VS: Top-K chunks
    VS->>CS: Reranked results
    CS->>LLM: Generate answer with context
    LLM->>CS: Streamed response
    CS->>FE: SSE stream with citations
    FE->>User: Display answer
```
