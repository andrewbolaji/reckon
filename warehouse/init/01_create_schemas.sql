-- Initialize warehouse schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

-- Read-only role for the MCP copilot: SELECT on marts only
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'reckon_reader') THEN
        CREATE ROLE reckon_reader LOGIN PASSWORD 'reckon_reader_dev';
    END IF;
END
$$;
GRANT USAGE ON SCHEMA marts TO reckon_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO reckon_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO reckon_reader;
