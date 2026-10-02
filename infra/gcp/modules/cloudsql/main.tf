# The serving database: gold.*, app.* (cases) and agent.trace_log.

resource "random_password" "db" {
  length  = 32
  special = false
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

    ip_configuration {
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
