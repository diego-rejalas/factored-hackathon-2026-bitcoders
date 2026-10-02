output "image_base" {
  description = "Registry path images are pushed to: <region>-docker.pkg.dev/<project>/<repo>."
  value       = "${var.region}-docker.pkg.dev/${google_artifact_registry_repository.images.project}/${google_artifact_registry_repository.images.repository_id}"
}

output "repository_id" {
  value = google_artifact_registry_repository.images.repository_id
}

output "repository_location" {
  value = google_artifact_registry_repository.images.location
}
