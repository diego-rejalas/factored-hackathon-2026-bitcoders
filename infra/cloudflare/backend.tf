# Remote state in the bucket that already holds the GCP state, under its own prefix. The bucket name is not written here:
# `terraform init -backend-config="bucket=<the state bucket>"`, as the GCP workflow does with GCP_STATE_BUCKET.
terraform {
  backend "gcs" {
    prefix = "cloudflare"
  }
}
