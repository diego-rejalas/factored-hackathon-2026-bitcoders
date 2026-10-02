# The ETL as a Cloud Run Job (S3 -> bronze -> dbt -> gold in Cloud SQL). Runs on demand.

resource "google_service_account" "this" {
  account_id   = var.name
  display_name = "Cloud Run Job ${var.name}"
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = var.secret_env
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.this.email}"
}

resource "google_project_iam_member" "cloudsql_client" {
  count   = var.enable_cloudsql ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.this.email}"
}

resource "google_storage_bucket_iam_member" "lakehouse" {
  bucket = var.lakehouse_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.this.email}"
}

resource "google_cloud_run_v2_job" "this" {
  name                = var.name
  location            = var.location
  deletion_protection = false
  labels              = var.labels

  template {
    template {
      service_account = google_service_account.this.email
      timeout         = var.timeout
      max_retries     = var.max_retries

      dynamic "volumes" {
        for_each = var.enable_cloudsql ? [1] : []
        content {
          name = "cloudsql"
          cloud_sql_instance {
            instances = [var.cloudsql_connection_name]
          }
        }
      }

      containers {
        image = var.image

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        dynamic "env" {
          for_each = var.env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }

        dynamic "volume_mounts" {
          for_each = var.enable_cloudsql ? [1] : []
          content {
            name       = "cloudsql"
            mount_path = "/cloudsql"
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.accessor,
    google_project_iam_member.cloudsql_client,
    google_storage_bucket_iam_member.lakehouse,
  ]
}
