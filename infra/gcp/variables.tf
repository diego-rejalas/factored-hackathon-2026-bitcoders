variable "project_id" {
  description = "GCP project that hosts the fallback stack."
  type        = string
}

variable "region" {
  description = "Region for every resource (Cloud SQL, Cloud Run, Artifact Registry)."
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Tag of the images in Artifact Registry to deploy (built by .github/workflows/gcp-deploy.yml)."
  type        = string
  default     = "latest"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is the cheapest Postgres tier (hackathon scale)."
  type        = string
  default     = "db-f1-micro"
}

variable "db_storage_gb" {
  description = "Cloud SQL storage in GB (auto-resize is on)."
  type        = number
  default     = 20
}

variable "db_deletion_protection" {
  description = "Set true once the fallback stack holds data you care about."
  type        = bool
  default     = false
}

variable "db_activation_policy" {
  description = "Cloud SQL activation policy: ALWAYS to run, NEVER to hibernate (saves compute and IP costs)."
  type        = string
  default     = "ALWAYS"
}

variable "openrouter_api_key" {
  description = "OpenRouter key for the fallback agent. Empty = deterministic fallback replies only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "typesafe_api_key" {
  description = "TypeSafe key for semantic intent classification. Empty = LLM/keyword classifier."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_model" {
  description = "Primary OpenRouter model for the agent."
  type        = string
  default     = "openai/gpt-4o-mini"
}

variable "guardrail_max_usd" {
  description = "Same product decision as Railway: auto-resolve only below this USD amount."
  type        = string
  default     = "500"
}

variable "lakehouse_bucket_name" {
  description = "Optional custom name for the GCS Lakehouse bucket. If empty, defaults to factored-lakehouse-<project_id>."
  type        = string
  default     = ""
}
