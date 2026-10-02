# Airflow on one Compute Engine VM: no external IP (IAP only), Shielded VM, OS Login, its own
# service account with the minimum it needs, a separate data disk with daily snapshots, and a
# nightly stop so it never keeps running by accident.

locals {
  compute_agent = "serviceAccount:service-${var.project_number}@compute-system.iam.gserviceaccount.com"
}

# --- identity -----------------------------------------------------------------

resource "google_service_account" "airflow" {
  account_id   = "${var.name}-sa"
  display_name = "Airflow VM ${var.name}"
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = var.secret_ids
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.airflow.email}"
}

resource "google_artifact_registry_repository_iam_member" "reader" {
  repository = var.registry_repository_id
  location   = var.registry_location
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.airflow.email}"
}

resource "google_storage_bucket_iam_member" "lake" {
  bucket = var.lake_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.airflow.email}"
}

# Logs and metrics for the Ops Agent.
resource "google_project_iam_member" "logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.airflow.email}"
}

resource "google_project_iam_member" "monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.airflow.email}"
}

# --- disks --------------------------------------------------------------------

resource "google_compute_disk" "data" {
  name   = "${var.name}-data"
  zone   = var.zone
  type   = "pd-balanced"
  size   = var.data_disk_gb
  labels = var.labels
}

resource "google_compute_resource_policy" "snapshots" {
  name   = "${var.name}-daily-snapshot"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "07:00" # UTC
      }
    }
    retention_policy {
      max_retention_days    = var.snapshot_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "snapshots" {
  name = google_compute_resource_policy.snapshots.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

# --- nightly stop -------------------------------------------------------------

resource "google_compute_resource_policy" "stop" {
  count  = var.auto_stop_enabled ? 1 : 0
  name   = "${var.name}-nightly-stop"
  region = var.region

  instance_schedule_policy {
    time_zone = var.auto_stop_time_zone
    vm_stop_schedule {
      schedule = var.auto_stop_cron
    }
  }
}

# The Compute Engine service agent is the one that stops and starts instances on a schedule.
resource "google_project_iam_member" "scheduler" {
  count   = var.auto_stop_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = local.compute_agent
}

# --- the VM -------------------------------------------------------------------

resource "google_compute_instance" "airflow" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["iap"] # the firewall in modules/network admits the IAP range for this tag
  labels       = var.labels

  deletion_protection       = var.deletion_protection
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.boot_disk_gb
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.self_link
    device_name = "airflow-data"
    mode        = "READ_WRITE"
  }

  # No access_config block: no external IP. Outbound traffic goes through Cloud NAT.
  network_interface {
    subnetwork = var.subnetwork_name
  }

  service_account {
    email  = google_service_account.airflow.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  resource_policies = var.auto_stop_enabled ? [google_compute_resource_policy.stop[0].id] : []

  metadata = {
    enable-oslogin         = "TRUE" # IAM-managed SSH
    block-project-ssh-keys = "TRUE"
    airflow-compose = templatefile("${path.module}/compose.yml.tftpl", {
      image               = var.image
      pg_host             = var.pg_host
      pg_port             = var.pg_port
      pg_user             = var.pg_user
      pg_database         = var.pg_database
      lake_bucket         = var.lake_bucket
      duckdb_memory_limit = var.duckdb_memory_limit
      duckdb_threads      = var.duckdb_threads
    })
    startup-script = templatefile("${path.module}/startup.sh.tftpl", {
      project_id        = var.project_id
      registry_location = var.registry_location
      airflow_db_host   = var.airflow_db_host
      airflow_db_name   = var.airflow_db_name
      airflow_db_user   = var.airflow_db_user
      secret_db         = var.secret_ids["airflow_db_password"]
      secret_fernet     = var.secret_ids["fernet_key"]
      secret_jwt        = var.secret_ids["api_jwt_secret"]
      secret_admin      = var.secret_ids["admin_password"]
      secret_pg         = var.secret_ids["pg_password"]
      secret_aws_id     = var.secret_ids["aws_id"]
      secret_aws_secret = var.secret_ids["aws_secret"]
    })
  }

  depends_on = [
    google_secret_manager_secret_iam_member.accessor,
    google_artifact_registry_repository_iam_member.reader,
    google_storage_bucket_iam_member.lake,
    google_compute_disk_resource_policy_attachment.snapshots,
  ]
}

# --- who may get in -----------------------------------------------------------

resource "google_iap_tunnel_instance_iam_member" "tunnel" {
  for_each = toset(var.admin_members)
  zone     = var.zone
  instance = google_compute_instance.airflow.name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = each.value
}

resource "google_compute_instance_iam_member" "os_login" {
  for_each      = toset(var.admin_members)
  zone          = var.zone
  instance_name = google_compute_instance.airflow.name
  role          = "roles/compute.osAdminLogin"
  member        = each.value
}

# OS Login on a VM that runs as a service account also needs serviceAccountUser on that account.
resource "google_service_account_iam_member" "ssh_as_sa" {
  for_each           = toset(var.admin_members)
  service_account_id = google_service_account.airflow.name
  role               = "roles/iam.serviceAccountUser"
  member             = each.value
}
