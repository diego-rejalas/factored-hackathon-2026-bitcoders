# Same bucket as the environments, own prefix. This stack is applied by a person (it creates the identity the
# pipeline uses to deploy), never by the pipeline itself.
terraform {
  backend "gcs" {
    bucket = "bitcoders-factored-hackathon-tfstate"
    prefix = "bootstrap"
  }
}
