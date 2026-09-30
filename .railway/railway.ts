import { defineRailway, github, group, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("postgres", { region: "us-east4-eqdc4a" });
  const airflowData = volume("airflow-data", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 5000 });
  // Bound by name to the volume actually attached to `postgres` (was named
  // "postgres-volume" in this file, but the live one is "data-volume--Z5O" —
  // that mismatch meant every edit here created an orphan instead of
  // resizing the real thing).
  const postgresVolume = volume("data-volume--Z5O", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-east4-eqdc4a", sizeMB: 30000 });
  // RETIRING. Idle since the ETL moved to the etl job; it stays only because
  // the etl service still references its two S3 credentials. Once they are set
  // directly on etl (see below) this service and the airflow-data volume are
  // deleted. Railway does not allow 0 replicas, so it keeps running until then.
  const railwayappAirflow = service("airflow", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/airflow/Dockerfile", watchPatterns: ["infra/airflow/**", "data/dags/**"] },
    healthcheck: "/api/v2/monitor/health",
    healthcheckTimeout: 1800,
    replicas: { "us-east4-eqdc4a": 1 },
    volumeMounts: { "/opt/airflow/data": airflowData },
    env: {
      AIRFLOW_UID: "50000",
      AIRFLOW__CORE__LOAD_EXAMPLES: "False",
      _AIRFLOW_WWW_USER_USERNAME: "admin",
      _AIRFLOW_WWW_USER_PASSWORD: preserve(),
      PG_HOST: Postgres.env.PGHOST,
      PG_PORT: Postgres.env.PGPORT,
      PG_USER: Postgres.env.PGUSER,
      PG_PASSWORD: Postgres.env.PGPASSWORD,
      PG_ADMIN_DATABASE: Postgres.env.PGDATABASE,
      PG_DATABASE: "data",
      LATAM_BANK_AWS_ACCESS_KEY_ID: preserve(),
      LATAM_BANK_AWS_SECRET_ACCESS_KEY: preserve(),
      AWS_REGION: "us-east-2",
    },
  });

  // One-shot ETL job (etl/run.py): S3 -> DuckDB -> dbt build -> Postgres gold.
  // It runs to completion on every deploy and a failed run is retried a bounded
  // number of times. Only etl/ and the dbt project trigger a redeploy.
  const etl = service("etl", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "etl/Dockerfile", watchPatterns: ["etl/**", "data/dbt/**"] },
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    env: {
      PG_HOST: Postgres.env.PGHOST,
      PG_PORT: Postgres.env.PGPORT,
      PG_USER: Postgres.env.PGUSER,
      PG_PASSWORD: Postgres.env.PGPASSWORD,
      PG_DATABASE: "data",
      // Read-only S3 credentials of the organizer. Referenced from the airflow
      // service (where they already live) so they are never read or copied here;
      // once airflow is retired they must be set on this service directly.
      LATAM_BANK_AWS_ACCESS_KEY_ID: railwayappAirflow.env.LATAM_BANK_AWS_ACCESS_KEY_ID,
      LATAM_BANK_AWS_SECRET_ACCESS_KEY: railwayappAirflow.env.LATAM_BANK_AWS_SECRET_ACCESS_KEY,
      AWS_REGION: "us-east-2",
    },
  });

  const dataPipeline = group("Data Pipeline", [Postgres, railwayappAirflow, etl, airflowData, postgresVolume]);

  return project("factored-hackathon", {
    resources: [dataPipeline],
  });
});
