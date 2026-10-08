# Puts the demo to sleep when nobody uses it and wakes it on request. The only part that does not wake by itself is
# Cloud SQL (Cloud Run scales from zero on the first request), so that is what this service starts and stops.
#
#   GET  /status         asleep, waking or awake            (public, through the load balancer under /waker/)
#   POST /wake           starts the database if it is stopped (public, idempotent)
#   POST /sleep-if-idle  stops it after idle_minutes without traffic (Cloud Scheduler only, checked by ID token)

locals {
  scheduler_audience = "${var.name}-scheduler"
}

# --- identity -----------------------------------------------------------------

resource "google_service_account" "scheduler" {
  account_id   = "${var.name}-sched"
  display_name = "Idle check of ${var.name}"
}

# The least the waker needs: read and patch the instance, read the Airflow VM's state. No create, delete, export or
# user management, which the predefined Cloud SQL roles would add.
resource "google_project_iam_custom_role" "waker" {
  role_id     = "${replace(var.name, "-", "_")}_role"
  title       = "Waker (${var.name})"
  description = "Read and patch the Cloud SQL instance and read the Airflow VM's state."
  permissions = [
    "cloudsql.instances.get",
    "cloudsql.instances.update",
    "compute.instances.get",
  ]
}

resource "google_project_iam_member" "custom" {
  project = var.project_id
  role    = google_project_iam_custom_role.waker.id
  member  = "serviceAccount:${module.service.service_account_email}"
}

# Reads the request count of the Cloud Run services to tell whether anyone is using the demo.
resource "google_project_iam_member" "monitoring" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${module.service.service_account_email}"
}

# --- the service --------------------------------------------------------------

module "service" {
  source = "../cloud_run_service"

  name       = var.name
  project_id = var.project_id
  location   = var.region
  image      = var.image

  env = {
    PROJECT_ID           = var.project_id
    SQL_INSTANCE         = var.sql_instance
    WATCH_SERVICES       = join(",", var.watch_services)
    IDLE_MINUTES         = tostring(var.idle_minutes)
    AIRFLOW_VM           = var.airflow_vm
    AIRFLOW_ZONE         = var.airflow_zone
    CORS_ALLOWED_ORIGINS = join(",", var.cors_allowed_origins)
    SCHEDULER_SA         = google_service_account.scheduler.email
    SCHEDULER_AUDIENCE   = local.scheduler_audience
  }

  # Public on purpose: a visitor's browser calls it. Everything it does that costs money or stops the demo is either
  # idempotent (wake) or checked by an ID token (sleep-if-idle). The load balancer's Cloud Armor rate-limits it.
  allow_unauthenticated = true
  ingress               = var.ingress
  min_instances         = 0
  max_instances         = 2
  deletion_protection   = var.deletion_protection
  labels                = var.labels
}

# --- the idle check -----------------------------------------------------------

resource "google_cloud_scheduler_job" "sleep_if_idle" {
  name        = "${var.name}-sleep-if-idle"
  region      = var.region
  description = "Stops the database when nobody used the demo for ${var.idle_minutes} minutes."
  schedule    = var.check_schedule
  time_zone   = "Etc/UTC"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${module.service.uri}/sleep-if-idle"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = local.scheduler_audience
    }
  }
}
