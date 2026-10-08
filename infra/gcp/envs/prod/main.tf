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

  # How workloads reach Cloud SQL (var.db_connectivity):
  #   public_ip  public IPv4 plus an authorized-networks allow-list (what the first stack did)
  #   connector  Cloud SQL connector, a unix socket; the apps read PG_HOST as a libpq/asyncpg
  #              host and both accept a socket directory, so no application change is needed
  #   private_ip private IP over Private Service Access; Cloud Run uses Direct VPC egress
  use_connector  = var.db_connectivity == "connector"
  use_private_ip = var.db_connectivity == "private_ip"

  db_host = (
    local.use_connector ? "/cloudsql/${module.cloudsql.connection_name}" :
    local.use_private_ip ? module.cloudsql.private_ip :
    module.cloudsql.public_ip
  )

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

module "network" {
  source = "../../modules/network"

  prefix               = local.prefix
  region               = var.region
  subnet_cidr          = var.subnet_cidr
  private_service_cidr = var.private_service_cidr
  enable_nat           = var.enable_nat || var.enable_airflow

  depends_on = [module.foundation]
}

module "cloudsql" {
  source = "../../modules/cloudsql"

  name                   = local.prefix
  region                 = var.region
  database_version       = var.db_version
  tier                   = var.db_tier
  disk_size_gb           = var.db_disk_gb
  availability_type      = var.db_availability_type
  deletion_protection    = var.db_deletion_protection
  point_in_time_recovery = var.db_point_in_time_recovery
  authorized_networks    = var.db_authorized_networks
  enable_public_ip       = !local.use_private_ip
  require_ssl            = var.db_require_ssl
  audit_logging          = var.db_audit_logging
  private_ip             = local.use_private_ip
  private_network_id     = module.network.network_id
  extra_databases        = var.enable_airflow ? { airflow = "airflow" } : {}
  service_users          = { backend = "backend_app", agent = "agent_app" }
  labels                 = local.labels

  depends_on = [module.foundation, module.network]
}

module "secrets" {
  source = "../../modules/secrets"

  prefix               = local.prefix
  db_password          = module.cloudsql.password
  enable_airflow       = var.enable_airflow
  airflow_db_password  = lookup(module.cloudsql.extra_passwords, "airflow", "")
  service_db_passwords = module.cloudsql.service_passwords
  openrouter_api_key   = var.openrouter_api_key
  typesafe_api_key     = var.typesafe_api_key
  labels               = local.labels

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

locals {
  edge_locked = var.enable_edge && var.edge_lockdown
  # Where the browser reaches the agent: the same origin as the page once the load balancer is the way in.
  agent_public_url = local.edge_locked ? "https://${module.edge[0].domain}/agent" : module.agent.uri
  edge_ingress     = local.edge_locked ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"

  # With the waker, the demo sleeps: Cloud Run scales to zero by itself, so the two services that need the database
  # never keep an instance (the waker stops and starts Cloud SQL, the one piece that does not wake on a request).
  backend_min_instances = var.enable_waker ? 0 : var.backend_min_instances
  agent_min_instances   = var.enable_waker ? 0 : var.agent_min_instances
  # Where the page asks whether the demo is awake: same origin, through the load balancer. Empty: no waiting screen.
  waker_path = var.enable_waker && local.edge_locked ? "/waker" : ""
}

module "backend" {
  source = "../../modules/cloud_run_service"

  name       = "${local.prefix}-backend"
  project_id = var.project_id
  location   = var.region
  image      = "${module.foundation.image_base}/backend:${var.image_tag}"

  env = merge(
    local.db_env,
    var.service_db_users ? { PG_USER = module.cloudsql.service_user_names["backend"] } : {},
    var.demo_accounts_enabled ? { DEMO_ACCOUNTS_ENABLED = "true", DEMO_PASSWORD = var.demo_password } : {},
    { GUARDRAIL_MAX_USD = var.guardrail_max_usd },
  )
  secret_env = {
    PG_PASSWORD        = module.secrets.secret_ids[var.service_db_users ? "backend-db-password" : "db-password"]
    SESSION_JWT_SECRET = module.secrets.secret_ids["session-jwt"]
    ADMIN_USERS        = module.secrets.secret_ids["admin-users"]
  }

  enable_cloudsql          = local.use_connector
  enable_vpc               = local.use_private_ip
  vpc_network              = module.network.network_name
  vpc_subnetwork           = module.network.subnetwork_name
  cloudsql_connection_name = module.cloudsql.connection_name
  allow_unauthenticated    = var.backend_public
  invoker_members          = var.backend_public ? [] : ["serviceAccount:${module.agent.service_account_email}"]
  min_instances            = local.backend_min_instances
  cpu_idle                 = var.run_cpu_idle
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

  env = merge(local.db_env, var.service_db_users ? { PG_USER = module.cloudsql.service_user_names["agent"] } : {}, {
    BANK_URL             = module.backend.uri
    BANK_IAM_AUDIENCE    = var.backend_public ? "" : module.backend.uri
    CORS_ALLOWED_ORIGINS = join(",", concat(var.cors_allowed_origins, var.enable_edge ? ["https://${module.edge[0].domain}"] : []))
    OPENROUTER_MODEL     = var.openrouter_model
    GUARDRAIL_MAX_USD    = var.guardrail_max_usd
  })
  secret_env = {
    PG_PASSWORD        = module.secrets.secret_ids[var.service_db_users ? "agent-db-password" : "db-password"]
    SESSION_JWT_SECRET = module.secrets.secret_ids["session-jwt"]
    OPENROUTER_API_KEY = module.secrets.secret_ids["openrouter-api-key"]
    TYPESAFE_API_KEY   = module.secrets.secret_ids["typesafe-api-key"]
  }

  enable_cloudsql          = local.use_connector
  enable_vpc               = local.use_private_ip
  vpc_network              = module.network.network_name
  vpc_subnetwork           = module.network.subnetwork_name
  cloudsql_connection_name = module.cloudsql.connection_name
  allow_unauthenticated    = true
  ingress                  = local.edge_ingress
  min_instances            = local.agent_min_instances
  cpu_idle                 = var.run_cpu_idle
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
    AGENT_URL = local.agent_public_url
    WAKER_URL = local.waker_path
  }

  allow_unauthenticated = true
  ingress               = local.edge_ingress
  cpu_idle              = var.run_cpu_idle
  deletion_protection   = var.run_deletion_protection
  labels                = local.labels

  depends_on = [module.foundation]
}

module "edge" {
  count  = var.enable_edge ? 1 : 0
  source = "../../modules/edge"

  name               = local.prefix
  project_id         = var.project_id
  region             = var.region
  frontend_service   = module.frontend.name
  agent_service      = module.agent.name
  domain             = var.edge_domain
  additional_domains = var.edge_additional_domains
  waker_service      = var.enable_waker ? module.waker[0].name : ""

  depends_on = [module.foundation]
}

# Stops Cloud SQL when nobody uses the demo and starts it when someone asks (see modules/waker).
module "waker" {
  count  = var.enable_waker ? 1 : 0
  source = "../../modules/waker"

  name           = "${local.prefix}-waker"
  project_id     = var.project_id
  region         = var.region
  image          = "${module.foundation.image_base}/waker:${var.image_tag}"
  sql_instance   = module.cloudsql.instance_name
  watch_services = [module.frontend.name, module.agent.name]
  airflow_vm     = var.enable_airflow ? "${local.prefix}-airflow" : ""
  airflow_zone   = var.airflow_zone
  idle_minutes   = var.waker_idle_minutes
  check_schedule = var.waker_check_schedule

  cors_allowed_origins = var.waker_allowed_origins
  ingress              = local.edge_ingress
  deletion_protection  = var.run_deletion_protection
  labels               = local.labels

  depends_on = [module.foundation]
}

# The waker is reached through the load balancer, so the route has to exist.
resource "terraform_data" "waker_requires_edge" {
  lifecycle {
    precondition {
      condition     = !var.enable_waker || var.enable_edge
      error_message = "enable_waker needs enable_edge: the waker is reached through the load balancer, under /waker/."
    }
  }
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
    GOLD_READER_ROLES   = module.cloudsql.service_user_names["backend"]
  })
  secret_env = {
    PG_PASSWORD                      = module.secrets.secret_ids["db-password"]
    LATAM_BANK_AWS_ACCESS_KEY_ID     = module.secrets.secret_ids["latam-bank-aws-id"]
    LATAM_BANK_AWS_SECRET_ACCESS_KEY = module.secrets.secret_ids["latam-bank-aws-secret"]
  }

  enable_cloudsql          = local.use_connector
  enable_vpc               = local.use_private_ip
  vpc_network              = module.network.network_name
  vpc_subnetwork           = module.network.subnetwork_name
  cloudsql_connection_name = module.cloudsql.connection_name
  lakehouse_bucket         = module.lakehouse.name
  labels                   = local.labels

  depends_on = [module.foundation]
}

data "google_project" "this" {
  count      = var.enable_airflow ? 1 : 0
  project_id = var.project_id
}

# Airflow reaches Cloud SQL over the VPC, so the database must have a private IP.
resource "terraform_data" "airflow_requires_private_db" {
  lifecycle {
    precondition {
      condition     = !var.enable_airflow || var.db_connectivity == "private_ip"
      error_message = "enable_airflow needs db_connectivity = private_ip: the VM connects to Cloud SQL over the private network."
    }
  }
}

module "airflow" {
  count  = var.enable_airflow ? 1 : 0
  source = "../../modules/airflow_vm"

  name           = "${local.prefix}-airflow"
  project_id     = var.project_id
  project_number = data.google_project.this[0].number
  region         = var.region
  zone           = var.airflow_zone
  machine_type   = var.airflow_machine_type
  data_disk_gb   = var.airflow_data_disk_gb

  network_name           = module.network.network_name
  subnetwork_name        = module.network.subnetwork_name
  image                  = "${module.foundation.image_base}/airflow:${var.image_tag}"
  registry_repository_id = module.foundation.repository_id
  registry_location      = module.foundation.repository_location
  lake_bucket            = module.lakehouse.name

  secret_ids = {
    airflow_db_password = module.secrets.secret_ids["airflow-db-password"]
    fernet_key          = module.secrets.secret_ids["airflow-fernet-key"]
    api_jwt_secret      = module.secrets.secret_ids["airflow-api-jwt-secret"]
    admin_password      = module.secrets.secret_ids["airflow-admin-password"]
    pg_password         = module.secrets.secret_ids["db-password"]
    aws_id              = module.secrets.secret_ids["latam-bank-aws-id"]
    aws_secret          = module.secrets.secret_ids["latam-bank-aws-secret"]
  }

  airflow_db_host   = module.cloudsql.private_ip
  pg_host           = module.cloudsql.private_ip
  pg_user           = module.cloudsql.user_name
  gold_reader_roles = module.cloudsql.service_user_names["backend"]
  pg_database       = module.cloudsql.database_name

  admin_members       = var.airflow_admin_members
  auto_stop_cron      = var.airflow_auto_stop_cron
  deletion_protection = var.run_deletion_protection
  labels              = local.labels

  depends_on = [module.foundation, module.network, terraform_data.airflow_requires_private_db]
}
