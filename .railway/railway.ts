import { defineRailway, github, group, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "us-east4-eqdc4a" });
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
      DBT_PG_DATABASE: Postgres.env.PGDATABASE,
    },
  });
  const railwayappAirflow = service("railwayapp-airflow", {
    source: github("diego-rejalas/factored-hackathon-2026-bitcoders", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "infra/airflow/Dockerfile" },
    healthcheck: "/api/v2/monitor/health",
    healthcheckTimeout: 1800,
    replicas: { "us-east4-eqdc4a": 1 },
    volumeMounts: { "/opt/airflow/data": airflowData },
    env: {
      AIRFLOW_UID: preserve(),
      AIRFLOW__CORE__LOAD_EXAMPLES: preserve(),
      _AIRFLOW_WWW_USER_PASSWORD: preserve(),
      _AIRFLOW_WWW_USER_USERNAME: preserve(),
      DBT_SERVICE_URL: dbt.env.RAILWAY_PRIVATE_DOMAIN,
    },
  });

  const dataPipeline = group("Data Pipeline", [Postgres, railwayappAirflow, dbt, airflowData, postgresVolume]);

  return project("factored-hackathon", {
    resources: [dataPipeline],
  });
});
