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
}

locals {
  prefix = "factored-${var.environment}"
  labels = {
    project     = "factored-hackathon"
    environment = var.environment
  }

  # Cloud Run reaches Cloud SQL either through the connector (unix socket, no network
  # allow-list) or over the public IP. The apps read PG_HOST as a libpq/asyncpg host, and
  # both accept a socket directory, so no application change is needed.
  db_host = var.use_cloud_sql_connector ? "/cloudsql/${module.cloudsql.connection_name}" : module.cloudsql.public_ip

  db_env = {
    PG_HOST     = local.db_host
    PG_PORT     = "5432"
    PG_USER     = module.cloudsql.user_name
    PG_DATABASE = module.cloudsql.database_name
  }
}

module "foundation" {
  source = "../../modules/foundation"

  region = var.region
  prefix = local.prefix
  labels = local.labels
}

module "cloudsql" {
  source = "../../modules/cloudsql"

  name                   = local.prefix
  region                 = var.region
  tier                   = var.db_tier
  disk_size_gb           = var.db_disk_gb
  availability_type      = var.db_availability_type
  deletion_protection    = var.db_deletion_protection
  point_in_time_recovery = var.db_point_in_time_recovery
  authorized_networks    = var.db_authorized_networks
  labels                 = local.labels

  depends_on = [module.foundation]
}

module "secrets" {
  source = "../../modules/secrets"

  prefix             = local.prefix
  db_password        = module.cloudsql.password
  openrouter_api_key = var.openrouter_api_key
  typesafe_api_key   = var.typesafe_api_key
  labels             = local.labels

  depends_on = [module.foundation]
}

module "lakehouse" {
  source = "../../modules/lakehouse"

  name          = "${local.prefix}-lakehouse-${var.project_id}"
  location      = var.region
  force_destroy = var.lakehouse_force_destroy
  labels        = local.labels

  depends_on = [module.foundation]
}

module "backend" {
  source = "../../modules/cloud_run_service"

  name       = "${local.prefix}-backend"
  project_id = var.project_id
  location   = var.region
  image      = "${module.foundation.image_base}/backend:${var.image_tag}"

  env = local.db_env
  secret_env = {
    PG_PASSWORD        = module.secrets.secret_ids["db-password"]
    SESSION_JWT_SECRET = module.secrets.secret_ids["session-jwt"]
  }

  enable_cloudsql          = var.use_cloud_sql_connector
  cloudsql_connection_name = module.cloudsql.connection_name
  allow_unauthenticated    = var.backend_public
  min_instances            = var.backend_min_instances
  deletion_protection      = var.run_deletion_protection
  labels                   = local.labels

  depends_on = [module.foundation]
}

module "agent" {
  source = "../../modules/cloud_run_service"

  name       = "${local.prefix}-agent"
  project_id = var.project_id
  location   = var.region
  image      = "${module.foundation.image_base}/agent:${var.image_tag}"

  env = merge(local.db_env, {
    BANK_URL          = module.backend.uri
    OPENROUTER_MODEL  = var.openrouter_model
    GUARDRAIL_MAX_USD = var.guardrail_max_usd
  })
  secret_env = {
    PG_PASSWORD        = module.secrets.secret_ids["db-password"]
    SESSION_JWT_SECRET = module.secrets.secret_ids["session-jwt"]
    OPENROUTER_API_KEY = module.secrets.secret_ids["openrouter-api-key"]
    TYPESAFE_API_KEY   = module.secrets.secret_ids["typesafe-api-key"]
  }

  enable_cloudsql          = var.use_cloud_sql_connector
  cloudsql_connection_name = module.cloudsql.connection_name
  allow_unauthenticated    = true
  min_instances            = var.agent_min_instances
  deletion_protection      = var.run_deletion_protection
  labels                   = local.labels

  depends_on = [module.foundation]
}

module "frontend" {
  source = "../../modules/cloud_run_service"

  name       = "${local.prefix}-frontend"
  project_id = var.project_id
  location   = var.region
  image      = "${module.foundation.image_base}/frontend:${var.image_tag}"

  env = {
    AGENT_URL = module.agent.uri
  }

  allow_unauthenticated = true
  deletion_protection   = var.run_deletion_protection
  labels                = local.labels

  depends_on = [module.foundation]
}

module "etl" {
  source = "../../modules/etl_job"

  name       = "${local.prefix}-etl"
  project_id = var.project_id
  location   = var.region
  image      = "${module.foundation.image_base}/etl:${var.image_tag}"

  env = merge(local.db_env, {
    AWS_REGION          = "us-east-2"
    DUCKDB_MEMORY_LIMIT = "8GB"
    DUCKDB_THREADS      = "4"
    LAKE_STORAGE_URI    = "gs://${module.lakehouse.name}"
  })
  secret_env = {
    PG_PASSWORD                      = module.secrets.secret_ids["db-password"]
    LATAM_BANK_AWS_ACCESS_KEY_ID     = module.secrets.secret_ids["latam-bank-aws-id"]
    LATAM_BANK_AWS_SECRET_ACCESS_KEY = module.secrets.secret_ids["latam-bank-aws-secret"]
  }

  enable_cloudsql          = var.use_cloud_sql_connector
  cloudsql_connection_name = module.cloudsql.connection_name
  lakehouse_bucket         = module.lakehouse.name
  labels                   = local.labels

  depends_on = [module.foundation]
}
