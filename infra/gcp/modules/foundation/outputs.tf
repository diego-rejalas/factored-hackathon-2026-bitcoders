output "image_base" {
  description = "Registry path images are pushed to: <region>-docker.pkg.dev/<project>/<repo>."
  value       = "${var.region}-docker.pkg.dev/${google_artifact_registry_repository.images.project}/${google_artifact_registry_repository.images.repository_id}"
}
