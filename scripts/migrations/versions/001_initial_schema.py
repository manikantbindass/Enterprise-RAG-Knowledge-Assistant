"""
Alembic Initial Schema Migration
Creates all tables, indexes, enums, triggers, and RLS policies
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')

    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('admin', 'manager', 'employee', 'viewer');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE document_status AS ENUM (
                'pending','uploading','uploaded','processing',
                'chunking','embedding','indexed','failed','archived'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE job_status AS ENUM ('queued','running','completed','failed','retrying');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE message_role AS ENUM ('user','assistant','system');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedback_type AS ENUM ('positive','negative','neutral');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # ── Organizations ────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("settings", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_documents", sa.Integer, nullable=False, server_default="10000"),
        sa.Column("max_users", sa.Integer, nullable=False, server_default="50"),
        sa.Column("max_storage_gb", sa.Integer, nullable=False, server_default="100"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_organizations_slug", "organizations", ["slug"])
    op.create_index("idx_organizations_is_active", "organizations", ["is_active"])

    # ── Users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("keycloak_id", sa.String(255), unique=True),
        sa.Column("role", sa.Text, nullable=False, server_default="employee"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("preferences", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )
    op.create_index("idx_users_org_id", "users", ["org_id"])
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_keycloak_id", "users", ["keycloak_id"])

    # ── Documents ────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", sa.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("department", sa.String(255)),
        sa.Column("tags", sa.ARRAY(sa.Text), server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("processing_errors", sa.ARRAY(sa.Text), server_default="{}"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("indexed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_documents_org_id", "documents", ["org_id"])
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_department", "documents", ["department"])
    op.create_index("idx_documents_created_at", "documents", ["created_at"])

    # ── Document Chunks (pgvector) ────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", sa.UUID, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("start_char", sa.Integer),
        sa.Column("end_char", sa.Integer),
        sa.Column("page_number", sa.Integer),
        sa.Column("embedding", Vector(1536)),
        sa.Column("chunking_strategy", sa.String(50), nullable=False, server_default="recursive"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("idx_chunks_org_id", "document_chunks", ["org_id"])

    # HNSW vector index
    op.execute("""
        CREATE INDEX idx_chunks_embedding_hnsw ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Full-text search index for BM25
    op.execute("""
        CREATE INDEX idx_chunks_content_fts ON document_chunks
        USING GIN(to_tsvector('english', content))
    """)

    # ── Conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("llm_provider", sa.String(50)),
        sa.Column("llm_model", sa.String(100)),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("share_token", sa.String(100), unique=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_conversations_org_id", "conversations", ["org_id"])
    op.create_index("idx_conversations_user_id", "conversations", ["user_id"])

    # ── Messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("conversation_id", sa.UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", sa.JSON, server_default="[]"),
        sa.Column("tokens_used", sa.Integer, server_default="0"),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0"),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("feedback", sa.Text),
        sa.Column("feedback_comment", sa.Text),
        sa.Column("is_regenerated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_messages_conversation_id", "messages", ["conversation_id"])

    # ── Processing Jobs ───────────────────────────────────────────────────────
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", sa.UUID, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("job_type", sa.String(50), nullable=False, server_default="full_pipeline"),
        sa.Column("chunks_created", sa.Integer, server_default="0"),
        sa.Column("embeddings_generated", sa.Integer, server_default="0"),
        sa.Column("embedding_cost", sa.Numeric(10, 6), server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_jobs_document_id", "processing_jobs", ["document_id"])
    op.create_index("idx_jobs_status", "processing_jobs", ["status"])

    # ── Audit Logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.UUID),
        sa.Column("before_state", sa.JSON),
        sa.Column("after_state", sa.JSON),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("session_id", sa.String(255)),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_audit_org_id", "audit_logs", ["org_id"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_created_at", "audit_logs", ["created_at"])

    # ── API Keys ──────────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("permissions", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("rate_limit_per_minute", sa.Integer, nullable=False, server_default="60"),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    # ── Usage Metrics ─────────────────────────────────────────────────────────
    op.create_table(
        "usage_metrics",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column("documents_uploaded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("documents_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("queries_made", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_input", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("embedding_cost", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("llm_cost", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("storage_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "metric_date", name="uq_usage_metrics_org_date"),
    )

    # ── Row Level Security ────────────────────────────────────────────────────
    for table in ["users", "documents", "document_chunks", "conversations", "messages"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # ── Auto-update triggers ──────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ["organizations", "users", "documents", "conversations"]:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)


def downgrade() -> None:
    for table in ["usage_metrics", "api_keys", "audit_logs", "processing_jobs",
                  "messages", "conversations", "document_chunks", "documents", "users", "organizations"]:
        op.drop_table(table)
    for enum in ["user_role", "document_status", "job_status", "message_role", "feedback_type"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
