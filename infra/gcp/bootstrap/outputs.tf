output "workload_identity_provider" {
  description = "Value of the repository variable GCP_WORKLOAD_IDENTITY_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "plan_service_account" {
  description = "Value of the repository variable GCP_PLAN_SA."
  value       = google_service_account.plan.email
}

output "deploy_service_account" {
  description = "Value of the repository variable GCP_DEPLOY_SA."
  value       = google_service_account.deploy.email
}
