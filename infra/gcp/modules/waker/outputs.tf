output "name" {
  value = module.service.name
}

output "uri" {
  value = module.service.uri
}

output "service_account_email" {
  value = module.service.service_account_email
}

output "scheduler_job" {
  value = google_cloud_scheduler_job.sleep_if_idle.name
}
