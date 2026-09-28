import { defineRailway, github, group, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("postgres", { region: "us-east4-eqdc4a" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const airflowData = volume("airflow-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 5000 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 5000 });
  const dbt = service("dbt", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/dbt/Dockerfile" },
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
    },
  });
  const railwayappAirflow = service("airflow", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/airflow/Dockerfile" },
    healthcheck: "/api/v2/monitor/health",
    healthcheckTimeout: 1800,
    replicas: { "us-east4-eqdc4a": 1 },
    volumeMounts: { "/opt/airflow/data": airflowData },
    env: {
      AIRFLOW_UID: "50000",
      AIRFLOW__CORE__LOAD_EXAMPLES: "False",
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

  const dataPipeline = group("Data Pipeline", [Postgres, railwayappAirflow, dbt, airflowData, postgresVolume]);

  return project("factored-hackathon", {
    resources: [dataPipeline],
  });
});
