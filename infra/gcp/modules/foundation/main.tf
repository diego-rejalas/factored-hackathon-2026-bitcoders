# Per-project plumbing every other module depends on: the APIs and the image registry.
# Callers add `depends_on = [module.foundation]` so nothing is created before the APIs are on.

resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iap.googleapis.com",
    "oslogin.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = var.prefix
  format        = "DOCKER"
  location      = var.region
  labels        = var.labels
  depends_on    = [google_project_service.services]
}
