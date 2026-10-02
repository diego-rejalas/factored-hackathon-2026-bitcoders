# Remote state, one prefix per environment, in the bucket created by scripts/setup-backend.sh.
# The state holds generated secrets (database password, JWT key): the bucket stays private.
terraform {
  backend "gcs" {
    bucket = "bitcoders-factored-hackathon-tfstate"
    prefix = "env/qa"
  }
}
