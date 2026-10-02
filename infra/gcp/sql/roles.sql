-- Database roles of the services. Run once as the owner (app) after Terraform has created the login roles,
-- and again after any change here. Every statement is idempotent.
--
--   infra/gcp/scripts/db_roles.sh
--
-- app            owner. Used by the pipeline (it rebuilds gold) and for administration.
-- backend_app    reads gold.*, owns the app schema (disputes and their events).
-- agent_app      owns the agent schema (the audit trail). It has no access to gold: the agent reads banking
--                data only through the backend.
--
-- Cloud SQL puts every user it creates in cloudsqlsuperuser; that membership is removed first.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backend_app')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_app') THEN
        RAISE EXCEPTION 'backend_app and agent_app must exist: apply the Terraform environment first';
    END IF;
END
$$;

REVOKE cloudsqlsuperuser FROM backend_app;
REVOKE cloudsqlsuperuser FROM agent_app;
ALTER ROLE backend_app NOCREATEDB NOCREATEROLE;
ALTER ROLE agent_app NOCREATEDB NOCREATEROLE;

-- PostgreSQL 16 and later let a role hand a schema to another only if it can SET ROLE to it. The owner (app)
-- administers both roles, so it gets membership in them; the services do not get any in each other.
GRANT backend_app TO app;
GRANT agent_app TO app;

-- The services run "create schema if not exists" at startup, and PostgreSQL checks the CREATE privilege on
-- the database before it looks at whether the schema exists. They can create schemas, not touch each other's.
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT, CREATE ON DATABASE %I TO backend_app, agent_app', current_database());
END
$$;

-- --- backend_app: owns app.*, reads gold.*
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION backend_app;
ALTER SCHEMA app OWNER TO backend_app;

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'app' LOOP
        EXECUTE format('ALTER TABLE app.%I OWNER TO backend_app', item.tablename);
    END LOOP;
    FOR item IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'app' LOOP
        EXECUTE format('ALTER SEQUENCE app.%I OWNER TO backend_app', item.sequencename);
    END LOOP;
END
$$;

GRANT USAGE ON SCHEMA gold TO backend_app;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO backend_app;
-- Tables the pipeline creates later in gold are readable from the start.
ALTER DEFAULT PRIVILEGES FOR ROLE app IN SCHEMA gold GRANT SELECT ON TABLES TO backend_app;

-- --- agent_app: owns agent.*
CREATE SCHEMA IF NOT EXISTS agent AUTHORIZATION agent_app;
ALTER SCHEMA agent OWNER TO agent_app;

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'agent' LOOP
        EXECUTE format('ALTER TABLE agent.%I OWNER TO agent_app', item.tablename);
    END LOOP;
    FOR item IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'agent' LOOP
        EXECUTE format('ALTER SEQUENCE agent.%I OWNER TO agent_app', item.sequencename);
    END LOOP;
END
$$;

-- --- Nothing else is open: no role but the owner reads another service's schema.
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON SCHEMA agent FROM PUBLIC;
REVOKE ALL ON SCHEMA gold FROM PUBLIC;
