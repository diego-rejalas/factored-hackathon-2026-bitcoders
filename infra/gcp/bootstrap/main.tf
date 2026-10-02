# GitHub Actions deploys to GCP without a stored key: each run exchanges the OIDC token GitHub issues for it
# (Workload Identity Federation) and impersonates a service account. Nothing long-lived exists to leak.

resource "google_project_service" "this" {
  for_each = toset([
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC tokens issued to GitHub Actions workflows"

  depends_on = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.actor"            = "assertion.actor"
    "attribute.repo_ref"         = "assertion.repository + '/' + assertion.ref"
  }

  # Without this condition any GitHub repository could ask for a token in this pool.
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# --- Plan: read-only. Any workflow of the repository (pull requests included) may use it.

resource "google_service_account" "plan" {
  account_id   = "github-plan"
  display_name = "GitHub Actions: terraform plan (read-only)"
}

resource "google_project_iam_member" "plan" {
  for_each = toset([
    "roles/viewer",
    "roles/iam.securityReviewer",
    "roles/secretmanager.viewer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.plan.email}"
}

# The plan reads the state and never writes it (the workflow runs it with -lock=false).
resource "google_storage_bucket_iam_member" "plan_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.plan.email}"
}

resource "google_service_account_iam_member" "plan_wif" {
  service_account_id = google_service_account.plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# --- Deploy: can change the infrastructure. Only workflows running on the deploy branch may use it.

resource "google_service_account" "deploy" {
  account_id   = "github-deploy"
  display_name = "GitHub Actions: terraform apply"
}

resource "google_project_iam_member" "deploy" {
  for_each = toset([
    "roles/run.admin",
    "roles/compute.admin",
    "roles/cloudsql.admin",
    "roles/secretmanager.admin",
    "roles/storage.admin",
    "roles/artifactregistry.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/resourcemanager.projectIamAdmin",
    "roles/servicenetworking.networksAdmin",
    "roles/vpcaccess.admin",
    "roles/iap.admin",
    "roles/serviceusage.serviceUsageAdmin",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repo_ref/${var.github_repository}/refs/heads/${var.deploy_branch}"
}
