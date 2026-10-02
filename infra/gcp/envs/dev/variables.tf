variable "project_id" {
  description = "GCP project of this environment."
  type        = string
}

variable "region" {
  description = "Region of every resource. us-east4 is the closest GCP region to the organizer's S3 bucket (us-east-2)."
  type        = string
  default     = "us-east4"
}

variable "environment" {
  description = "Environment name; prefixes every resource (factored-<environment>)."
  type        = string
  default     = "dev"
}

variable "image_tag" {
  description = "Tag of the images in Artifact Registry to deploy (the git SHA, set by CI)."
  type        = string
  default     = "latest"
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-f1-micro"
}

variable "db_disk_gb" {
  type    = number
  default = 20
}

variable "db_availability_type" {
  description = "ZONAL, or REGIONAL for high availability (roughly double the cost)."
  type        = string
  default     = "ZONAL"
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "db_point_in_time_recovery" {
  type    = bool
  default = false
}

variable "use_cloud_sql_connector" {
  description = <<-EOT
    true: Cloud Run and the ETL job reach Cloud SQL through the connector (no network allow-list).
    false: they connect over the public IP, which needs db_authorized_networks.
  EOT
  type        = bool
  default     = false
}

variable "db_authorized_networks" {
  description = "CIDR ranges allowed over the public IP. Empty when use_cloud_sql_connector is true."
  type = list(object({
    name = string
    cidr = string
  }))
  default = [{ name = "dev-open-password-only", cidr = "0.0.0.0/0" }]
}

variable "backend_public" {
  description = "Open the backend to the internet. The agent calls it without an ID token today, so it stays true until the agent authenticates."
  type        = bool
  default     = true
}

variable "backend_min_instances" {
  type    = number
  default = 0
}

variable "agent_min_instances" {
  type    = number
  default = 0
}

variable "run_deletion_protection" {
  description = "Block terraform destroy on the Cloud Run services."
  type        = bool
  default     = false
}

variable "lakehouse_force_destroy" {
  description = "Allow terraform destroy to delete the bucket together with its objects."
  type        = bool
  default     = true
}

variable "openrouter_api_key" {
  description = "OpenRouter key. Empty means the agent runs on deterministic replies only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "typesafe_api_key" {
  description = "TypeSafe key. Empty means the LLM or keyword classifier is used."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_model" {
  type    = string
  default = "openai/gpt-4o-mini"
}

variable "guardrail_max_usd" {
  description = "Product decision: auto-resolve only below this USD amount."
  type        = string
  default     = "500"
}
