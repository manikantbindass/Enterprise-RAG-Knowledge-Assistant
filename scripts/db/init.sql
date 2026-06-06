-- Database initialization script
-- Runs on first postgres container start

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Keycloak schema (Keycloak needs its own schema in the same DB)
CREATE SCHEMA IF NOT EXISTS keycloak;
GRANT ALL PRIVILEGES ON SCHEMA keycloak TO rag_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA keycloak TO rag_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA keycloak GRANT ALL ON TABLES TO rag_user;

-- Set search path
ALTER DATABASE rag_assistant SET search_path TO public;
