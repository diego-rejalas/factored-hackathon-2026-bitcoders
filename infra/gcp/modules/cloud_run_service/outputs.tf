output "uri" {
  value = google_cloud_run_v2_service.this.uri
}

output "name" {
  value = google_cloud_run_v2_service.this.name
}

output "service_account_email" {
  value = google_service_account.this.email
}
