import { defineRailway, github, group, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("postgres", { region: "us-east4-eqdc4a" });
  // Airflow's own metadata DB (DAG runs, task states). Kept apart from the
  // data Postgres so an Airflow problem can't touch bronze/silver/gold, and
  // replaces the single-writer SQLite file that used to live on the volume.
  const AirflowDb = postgres("airflow-db", { region: "us-east4-eqdc4a" });
  const airflowData = volume("airflow-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 5000 });
  // Bound by name to the volume actually attached to `postgres` (was named
  // "postgres-volume" in this file, but the live one is "data-volume--Z5O" —
  // that mismatch meant every edit here created an orphan instead of
  // resizing the real thing).
  const postgresVolume = volume("data-volume--Z5O", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 30000 });
  const dbt = service("dbt", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    // Redeploy only when something baked into this image changes (see
    // infra/dbt/Dockerfile COPY lines) — a docs-only push must not restart it.
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/dbt/Dockerfile", watchPatterns: ["infra/dbt/**", "data/dbt/**"] },
    healthcheck: "/health",
    replicas: { "us-east4-eqdc4a": 1 },
    env: {
      DBT_PG_HOST: Postgres.env.PGHOST,
      DBT_PG_PORT: Postgres.env.PGPORT,
      DBT_PG_USER: Postgres.env.PGUSER,
      DBT_PG_PASSWORD: Postgres.env.PGPASSWORD,
      // The DAG bootstraps this application database from the managed
      // Postgres database on its first run.
      DBT_PG_DATABASE: "data",
      // Railway's private networking implies port 80 when a consumer uses
      // RAILWAY_PRIVATE_DOMAIN with no port suffix. Pinning this service to
      // listen there avoids needing to concatenate a port onto the domain
      // reference object below (that produced a literal "[object Object]:8000"
      // string — env refs aren't plain strings until Railway resolves them).
      PORT: "80",
    },
  });
  const railwayappAirflow = service("airflow", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    // Same idea: only infra/airflow (Dockerfile, entrypoint, requirements) and
    // data/dags (copied into the image) should trigger a redeploy.
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/airflow/Dockerfile", watchPatterns: ["infra/airflow/**", "data/dags/**"] },
    healthcheck: "/api/v2/monitor/health",
    healthcheckTimeout: 1800,
    replicas: { "us-east4-eqdc4a": 1 },
    volumeMounts: { "/opt/airflow/data": airflowData },
    env: {
      AIRFLOW_UID: "50000",
      AIRFLOW__CORE__LOAD_EXAMPLES: "False",
      // SQLAlchemy accepts the postgresql:// scheme Railway provides (psycopg2).
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: AirflowDb.env.DATABASE_URL,
      // Literal, not preserve() — this service has been recreated a few
      // times during setup (renames), and preserve() has nothing to carry
      // forward on a brand-new resource, which silently dropped this var
      // and broke login. Not a secret, safe to commit.
      _AIRFLOW_WWW_USER_USERNAME: "admin",
      _AIRFLOW_WWW_USER_PASSWORD: preserve(),
      DBT_SERVICE_URL: dbt.env.RAILWAY_PRIVATE_DOMAIN,
      // ingest_latam_bank DAG: S3 -> data.bronze.*
      PG_HOST: Postgres.env.PGHOST,
      PG_PORT: Postgres.env.PGPORT,
      PG_USER: Postgres.env.PGUSER,
      PG_PASSWORD: Postgres.env.PGPASSWORD,
      // Railway's provisioned database is used only to create `data`.
      PG_ADMIN_DATABASE: Postgres.env.PGDATABASE,
      PG_DATABASE: "data",
      // read-only S3 credentials from the data dictionary — set directly in
      // Railway, never committed here (preserve() keeps whatever's already set).
      LATAM_BANK_AWS_ACCESS_KEY_ID: preserve(),
      LATAM_BANK_AWS_SECRET_ACCESS_KEY: preserve(),
      AWS_REGION: "us-east-2",
    },
  });

  const dataPipeline = group("Data Pipeline", [Postgres, AirflowDb, railwayappAirflow, dbt, airflowData, postgresVolume]);

  return project("factored-hackathon", {
    resources: [dataPipeline],
  });
});
