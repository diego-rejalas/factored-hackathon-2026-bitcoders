import { defineRailway, github, group, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const REPO = "diego-rejalas/factored-hackathon-2026-bitcoders";
  const REGION = "us-east4-eqdc4a";

  // Serving database: gold.* (what backend/ reads), bronze/silver (written by the
  // DAG and dbt), ops.etl_runs.
  const Postgres = postgres("postgres", { region: REGION });
  // Bound by name to the volume actually attached to `postgres` (the live one is
  // "data-volume--Z5O"; declaring a different name creates an orphan instead of
  // resizing the real thing).
  const postgresVolume = volume("data-volume--Z5O", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: REGION, sizeMB: 30000 });

  // Airflow's own metadata DB (DAG runs, task states), apart from the data
  // Postgres so an Airflow problem can't touch bronze/silver/gold.
  const AirflowDb = postgres("airflow-db", { region: REGION });
  const airflowData = volume("airflow-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: REGION, sizeMB: 5000 });

  // dbt as its own service: its dependencies clash with Airflow's constraints
  // file, and it stays visible as a piece of its own. The DAG calls POST /run.
  const dbt = service("dbt", {
    source: github(REPO, { checkSuites: false, rootDirectory: "/" }),
    // Redeploy only when something baked into this image changes (see
    // infra/dbt/Dockerfile COPY lines): a docs-only push must not restart it.
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/dbt/Dockerfile", watchPatterns: ["infra/dbt/**", "data/dbt/**"] },
    healthcheck: "/health",
    replicas: { [REGION]: 1 },
    env: {
      DBT_PG_HOST: Postgres.env.PGHOST,
      DBT_PG_PORT: Postgres.env.PGPORT,
      DBT_PG_USER: Postgres.env.PGUSER,
      DBT_PG_PASSWORD: Postgres.env.PGPASSWORD,
      DBT_PG_DATABASE: "data",
      // Railway's private networking implies port 80 when a consumer uses
      // RAILWAY_PRIVATE_DOMAIN with no port suffix. Pinning this service to
      // listen there avoids concatenating a port onto the domain reference
      // below (env refs are not plain strings until Railway resolves them).
      PORT: "80",
    },
  });

  const airflow = service("airflow", {
    source: github(REPO, { checkSuites: false, rootDirectory: "/" }),
    // Only infra/airflow (Dockerfile, entrypoint, requirements) and data/dags
    // (copied into the image) should trigger a redeploy.
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/airflow/Dockerfile", watchPatterns: ["infra/airflow/**", "data/dags/**"] },
    healthcheck: "/api/v2/monitor/health",
    healthcheckTimeout: 1800,
    replicas: { [REGION]: 1 },
    volumeMounts: { "/opt/airflow/data": airflowData },
    env: {
      AIRFLOW_UID: "50000",
      AIRFLOW__CORE__LOAD_EXAMPLES: "False",
      // SQLAlchemy accepts the postgresql:// scheme Railway provides (psycopg2).
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: AirflowDb.env.DATABASE_URL,
      _AIRFLOW_WWW_USER_USERNAME: "admin",
      _AIRFLOW_WWW_USER_PASSWORD: preserve(),
      DBT_SERVICE_URL: dbt.env.RAILWAY_PRIVATE_DOMAIN,
      // DAG latam_bank_pipeline: DuckDB writes S3 -> bronze.* in this Postgres.
      PG_HOST: Postgres.env.PGHOST,
      PG_PORT: Postgres.env.PGPORT,
      PG_USER: Postgres.env.PGUSER,
      PG_PASSWORD: Postgres.env.PGPASSWORD,
      PG_DATABASE: "data",
      // Read-only S3 credentials of the organizer, set directly in Railway and
      // never committed here (preserve() keeps whatever is already set).
      LATAM_BANK_AWS_ACCESS_KEY_ID: preserve(),
      LATAM_BANK_AWS_SECRET_ACCESS_KEY: preserve(),
      AWS_REGION: "us-east-2",
    },
  });

  const dataPipeline = group("Data Pipeline", [Postgres, AirflowDb, airflow, dbt, airflowData, postgresVolume]);

  return project("factored-hackathon", {
    resources: [dataPipeline],
  });
});
