# The serving database: gold.*, app.* (cases) and agent.trace_log.

resource "random_password" "db" {
  length  = 32
  special = false
}

locals {
  audit_flags = var.audit_logging ? {
    log_checkpoints         = "on"
    log_connections         = "on"
    log_disconnections      = "on"
    log_lock_waits          = "on"
    log_temp_files          = "0"
    log_statement           = "ddl"
    log_min_messages        = "warning"
    log_min_error_statement = "error"
  } : {}
}

resource "google_sql_database_instance" "postgres" {
  name                = var.name
  database_version    = var.database_version
  region              = var.region
  deletion_protection = var.deletion_protection

  settings {
    # ENTERPRISE (not the new default ENTERPRISE_PLUS): shared-core tiers only exist here.
    edition           = "ENTERPRISE"
    tier              = var.tier
    availability_type = var.availability_type
    disk_size         = var.disk_size_gb
    disk_autoresize   = true
    activation_policy = var.activation_policy
    user_labels       = var.labels

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.point_in_time_recovery
    }

    dynamic "database_flags" {
      for_each = local.audit_flags
      content {
        name  = database_flags.key
        value = database_flags.value
      }
    }

    ip_configuration {
      ssl_mode        = var.require_ssl ? "ENCRYPTED_ONLY" : "ALLOW_UNENCRYPTED_AND_ENCRYPTED"
      ipv4_enabled    = var.enable_public_ip
      private_network = var.private_ip ? var.private_network_id : null
      dynamic "authorized_networks" {
        for_each = var.authorized_networks
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.cidr
        }
      }
    }
  }

  # The waker (modules/waker) and scripts/manage_db.sh stop and start the instance by patching the activation policy, and
  # the waker stamps the time of the last wake in a label. Without this an `apply` would put both back to what the code says
  # and wake a sleeping database. The variable only decides the policy at creation.
  lifecycle {
    ignore_changes = [settings[0].activation_policy, settings[0].user_labels]
  }
}

resource "google_sql_database" "data" {
  name     = var.database_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = var.user_name
  instance = google_sql_database_instance.postgres.name
  password = random_password.db.result
}

resource "random_password" "extra" {
  for_each = var.extra_databases
  length   = 32
  special  = false
}

resource "google_sql_database" "extra" {
  for_each = var.extra_databases
  name     = each.key
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "extra" {
  for_each = var.extra_databases
  name     = each.value
  instance = google_sql_database_instance.postgres.name
  password = random_password.extra[each.key].result
}

resource "random_password" "service" {
  for_each = var.service_users
  length   = 32
  special  = false
}

resource "google_sql_user" "service" {
  for_each = var.service_users
  name     = each.value
  instance = google_sql_database_instance.postgres.name
  password = random_password.service[each.key].result
}
