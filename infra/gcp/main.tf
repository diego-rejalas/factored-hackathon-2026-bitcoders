# Migración completa a GCP (primario desde esta rama): Railway queda como
# legacy en transición (.railway/railway.ts ya no se aplica). Todo el stack
# vive acá: Cloud SQL, Cloud Run (backend, agent, dbt, frontend) y el Job ETL.

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # The state bucket must exist before the first apply — see infra/gcp/README.md.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- APIs -------------------------------------------------------------------

resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# --- Artifact Registry (images built by .github/workflows/gcp-deploy.yml) ---

resource "google_artifact_registry_repository" "images" {
  repository_id = "factored-hackathon"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.services]
}

# --- Secret Manager ----------------------------------------------------------

resource "random_password" "db" {
  length  = 32
  special = false
}

# Shared between the backend (issuer) and the agent (fail-fast pre-check);
# regenerated per stack, so Railway and GCP sessions are independent.
resource "random_password" "session_jwt" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(["session-jwt-secret", "openrouter-api-key", "typesafe-api-key"])
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "versions" {
  for_each = {
    "session-jwt-secret" = random_password.session_jwt.result
    "openrouter-api-key" = coalesce(var.openrouter_api_key, "NOT_SET")
    "typesafe-api-key"   = coalesce(var.typesafe_api_key, "NOT_SET")
  }
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value
}

# --- Cloud SQL (the serving database: gold.*, app.*, agent.trace_log) --------

resource "google_sql_database_instance" "postgres" {
  name             = "factored-hackathon"
  database_version = "POSTGRES_16"
  region           = var.region
  # Hackathon fallback: false so `terraform destroy` actually tears it down.
  deletion_protection = var.db_deletion_protection
  settings {
    # ENTERPRISE (not the new default ENTERPRISE_PLUS): the cheap shared-core
    # tiers (db-f1-micro) only exist under this edition.
    edition           = "ENTERPRISE"
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = var.db_storage_gb
    disk_autoresize   = true
    activation_policy = var.db_activation_policy
    backup_configuration {
      enabled = true
    }
    # Public IP with password auth. Authorized networks 0.0.0.0/0 is required:
    # an empty list blocks ALL external access (which is why connections timed
    # out). Zero-code-change compromise so Cloud Run + local psql can connect;
    # hardening paths are in the README.
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "hackathon-open-password-only"
        value = "0.0.0.0/0"
      }
    }
  }
  depends_on = [google_project_service.services]
}

resource "google_sql_database" "data" {
  name     = "data"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.postgres.name
  password = random_password.db.result
}

# --- Common Cloud SQL wiring -------------------------------------------------

locals {
  registry   = "${var.region}-docker.pkg.dev"
  image_base = "${local.registry}/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
  db_env = {
    PG_HOST     = google_sql_database_instance.postgres.public_ip_address
    PG_PORT     = "5432"
    PG_USER     = google_sql_user.app.name
    PG_PASSWORD = random_password.db.result
    PG_DATABASE = google_sql_database.data.name
  }
  common_labels = {
    project = "factored-hackathon"
    role    = "fallback-stack"
  }
}

# --- Cloud Run: backend (vertical 3, same Dockerfile as Railway) -------------

resource "google_cloud_run_v2_service" "backend" {
  name                = "backend"
  location            = var.region
  deletion_protection = false
  labels              = local.common_labels
  template {
    containers {
      image = "${local.image_base}/backend:${var.image_tag}"
      dynamic "env" {
        for_each = local.db_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "SESSION_JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["session-jwt-secret"].id
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [
    google_project_service.services,
    google_sql_database.data,
    google_secret_manager_secret_version.versions,
  ]
}

resource "google_cloud_run_v2_service_iam_binding" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# --- Cloud Run: agent (vertical 4, same Dockerfile as Railway) ---------------

resource "google_cloud_run_v2_service" "agent" {
  name                = "agent"
  location            = var.region
  deletion_protection = false
  labels              = local.common_labels
  template {
    containers {
      image = "${local.image_base}/agent:${var.image_tag}"
      env {
        name  = "BANK_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
      env {
        name = "SESSION_JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["session-jwt-secret"].id
            version = "latest"
          }
        }
      }
      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["openrouter-api-key"].id
            version = "latest"
          }
        }
      }
      env {
        name  = "OPENROUTER_MODEL"
        value = var.openrouter_model
      }
      env {
        name = "TYPESAFE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["typesafe-api-key"].id
            version = "latest"
          }
        }
      }
      env {
        name  = "GUARDRAIL_MAX_USD"
        value = var.guardrail_max_usd
      }
      dynamic "env" {
        for_each = local.db_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  depends_on = [
    google_project_service.services,
    google_cloud_run_v2_service.backend,
    google_secret_manager_secret_version.versions,
  ]
}

resource "google_cloud_run_v2_service_iam_binding" "agent_public" {
  name     = google_cloud_run_v2_service.agent.name
  location = var.region
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# --- Cloud Run: frontend (Next.js standalone, same repo Dockerfile) ----------

resource "google_cloud_run_v2_service" "frontend" {
  name                = "frontend"
  location            = var.region
  deletion_protection = false
  labels              = local.common_labels
  template {
    containers {
      image = "${local.image_base}/frontend:${var.image_tag}"
      env {
        name  = "AGENT_URL"
        value = google_cloud_run_v2_service.agent.uri
      }
    }
  }
  depends_on = [
    google_project_service.services,
    google_cloud_run_v2_service.agent,
  ]
}

resource "google_cloud_run_v2_service_iam_binding" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

# --- Cloud Run Job: ETL (S3 -> bronze -> dbt, no Airflow) --------------------

resource "google_cloud_run_v2_job" "etl" {
  name     = "etl"
  location = var.region
  labels   = local.common_labels
  template {
    template {
      service_account = google_service_account.etl.email
      # Loads (~40 min from S3 cross-cloud into f1-micro Cloud SQL) + dbt build.
      timeout     = "7200s"
      max_retries = 1
      containers {
        image = "${local.image_base}/etl:${var.image_tag}"
        resources {
          limits = {
            # 16Gi requires >= 4 CPU in Cloud Run (2 CPU caps memory at 8Gi).
            memory = "16Gi"
            cpu    = "4"
          }
        }
        dynamic "env" {
          for_each = local.db_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "LATAM_BANK_AWS_ACCESS_KEY_ID"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.aws["latam-bank-aws-id"].id
              version = "latest"
            }
          }
        }
        env {
          name = "LATAM_BANK_AWS_SECRET_ACCESS_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.aws["latam-bank-aws-secret"].id
              version = "latest"
            }
          }
        }
        env {
          name  = "AWS_REGION"
          value = "us-east-2"
        }
        env {
          name  = "DUCKDB_MEMORY_LIMIT"
          value = "8GB"
        }
        env {
          name  = "DUCKDB_THREADS"
          value = "4"
        }
      }
    }
  }
  depends_on = [
    google_project_service.services,
    google_secret_manager_secret_version.aws,
  ]
}

# The organizer's read-only S3 credentials live in Railway (preserve()); the
# fallback job reads them from Secret Manager instead of committing them here.
resource "google_secret_manager_secret" "aws" {
  for_each  = toset(["latam-bank-aws-id", "latam-bank-aws-secret"])
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.services]
}

# Placeholder versions so the job can deploy before real credentials are
# copied in (extract_load fails fast with a clear message if they are empty).
resource "google_secret_manager_secret_version" "aws" {
  for_each = {
    "latam-bank-aws-id"     = "NOT_SET"
    "latam-bank-aws-secret" = "NOT_SET"
  }
  secret      = google_secret_manager_secret.aws[each.key].id
  secret_data = each.value
}

resource "google_service_account" "etl" {
  account_id   = "etl-job"
  display_name = "Cloud Run Job: fallback ETL"
}

# The Run services use the project's default compute service account, which
# must read the Secret Manager values they mount (JWT, LLM keys).
data "google_compute_default_service_account" "default" {}

resource "google_project_iam_member" "run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

resource "google_project_iam_member" "etl_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.etl.email}"
}

resource "google_cloud_run_v2_job_iam_binding" "etl_executor" {
  name     = google_cloud_run_v2_job.etl.name
  location = var.region
  role     = "roles/run.invoker"
  members  = ["serviceAccount:${google_service_account.etl.email}"]
}

# --- Outputs ------------------------------------------------------------------

output "backend_uri" {
  value = google_cloud_run_v2_service.backend.uri
}

output "agent_uri" {
  value = google_cloud_run_v2_service.agent.uri
}

output "frontend_uri" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "cloudsql_public_ip" {
  value     = google_sql_database_instance.postgres.public_ip_address
  sensitive = false
}
