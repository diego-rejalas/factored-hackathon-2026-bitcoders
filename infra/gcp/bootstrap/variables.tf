variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "github_repository" {
  description = "owner/name of the repository whose workflows may deploy. Tokens from any other repository are rejected by the provider itself."
  type        = string
  default     = "diego-rejalas/factored-hackathon-2026-bitcoders"
}

variable "deploy_branch" {
  description = "Branch whose workflows may use the deployment account."
  type        = string
  default     = "main"
}

variable "state_bucket" {
  description = "Bucket with the Terraform state of the environments."
  type        = string
  default     = "bitcoders-factored-hackathon-tfstate"
}
