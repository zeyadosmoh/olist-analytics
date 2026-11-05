-- Read-only Postgres user for Metabase.
-- It can only SELECT from tables in the "marts" schema.
--
-- The password is NOT stored here. psql fills in :'mb_password' at run time.
-- Run it through scripts/create_metabase_ro.sh (reads MB_DB_PASSWORD from .env).
-- Safe to run more than once.

\set ON_ERROR_STOP on

-- 1) Create the login role if it does not exist yet.
SELECT 'CREATE ROLE metabase_ro LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metabase_ro')
\gexec

-- 2) Set (or reset) the password and make every session read-only.
ALTER ROLE metabase_ro WITH LOGIN PASSWORD :'mb_password';
ALTER ROLE metabase_ro SET default_transaction_read_only = on;

-- 3) Only connect + read access to the marts schema.
GRANT CONNECT ON DATABASE olist TO metabase_ro;
REVOKE ALL ON SCHEMA public FROM metabase_ro;
GRANT USAGE ON SCHEMA marts TO metabase_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO metabase_ro;

-- 4) dbt drops and re-creates mart tables on every run, which removes grants.
--    Default privileges give SELECT on every new table that the dbt user
--    (the current user) creates in marts.
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO metabase_ro;
