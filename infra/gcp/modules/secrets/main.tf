# Every secret of the environment. Values are mounted into Cloud Run as env vars by id;
# nothing sensitive is written into a service definition.

# Shared by the backend (issuer) and the agent (fail-fast pre-check).
resource "random_password" "session_jwt" {
  length  = 64
  special = false
}

# Airflow. The Fernet key must be 32 url-safe base64 bytes: 43 characters without padding, plus "=".
resource "random_id" "airflow_fernet" {
  count       = var.enable_airflow ? 1 : 0
  byte_length = 32
}

resource "random_password" "airflow_jwt" {
  count   = var.enable_airflow ? 1 : 0
  length  = 64
  special = false
}

resource "random_password" "airflow_admin" {
  count   = var.enable_airflow ? 1 : 0
  length  = 24
  special = false
}

locals {
  # Static names so for_each never depends on a sensitive value.
  airflow_secret_names = var.enable_airflow ? ["airflow-db-password", "airflow-fernet-key", "airflow-api-jwt-secret", "airflow-admin-password"] : []

  secret_names = toset(concat([
    "session-jwt",
    "db-password",
    "backend-db-password",
    "agent-db-password",
    "openrouter-api-key",
    "typesafe-api-key",
    "latam-bank-aws-id",
    "latam-bank-aws-secret",
  ], local.airflow_secret_names))

  manual_secret_names = toset(["latam-bank-aws-id", "latam-bank-aws-secret"])

  airflow_secret_values = var.enable_airflow ? {
    "airflow-db-password"    = var.airflow_db_password
    "airflow-fernet-key"     = "${random_id.airflow_fernet[0].b64_url}="
    "airflow-api-jwt-secret" = random_password.airflow_jwt[0].result
    "airflow-admin-password" = random_password.airflow_admin[0].result
  } : {}

  secret_values = merge(local.airflow_secret_values, {
    "session-jwt"         = random_password.session_jwt.result
    "db-password"         = var.db_password
    "backend-db-password" = lookup(var.service_db_passwords, "backend", "NOT_SET")
    "agent-db-password"   = lookup(var.service_db_passwords, "agent", "NOT_SET")
    "openrouter-api-key"  = coalesce(var.openrouter_api_key, "NOT_SET")
    "typesafe-api-key"    = coalesce(var.typesafe_api_key, "NOT_SET")
    # The organizer's read-only S3 keys are copied in by hand after the first apply
    # (never through Terraform variables or git); the ETL fails fast while they are NOT_SET.
    "latam-bank-aws-id"     = "NOT_SET"
    "latam-bank-aws-secret" = "NOT_SET"
  })
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secret_names
  secret_id = "${var.prefix}-${each.key}"
  labels    = var.labels
  replication {
    auto {}
  }
}

# Generated or variable-driven values: Terraform owns them, so a rotation propagates.
resource "google_secret_manager_secret_version" "managed" {
  for_each    = setsubtract(local.secret_names, local.manual_secret_names)
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = local.secret_values[each.key]
}

# Placeholders only: the real value is added by hand as a new version, and a later
# apply must not roll it back.
resource "google_secret_manager_secret_version" "manual" {
  for_each    = local.manual_secret_names
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = local.secret_values[each.key]

  lifecycle {
    ignore_changes = [secret_data]
  }
}
