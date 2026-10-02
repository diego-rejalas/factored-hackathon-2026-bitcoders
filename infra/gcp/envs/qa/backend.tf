# The state bucket is created once by scripts/setup-backend.sh and passed at init time:
#   terraform init -backend-config="bucket=<PROJECT_ID>-tfstate"
terraform {
  backend "gcs" {
    prefix = "factored/qa"
  }
}
