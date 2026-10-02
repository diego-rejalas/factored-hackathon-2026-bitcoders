variable "name" {
  description = "Job name; also the service account id (30 characters or fewer)."
  type        = string
}

variable "project_id" {
  type = string
}

variable "location" {
  type = string
}

variable "image" {
  type = string
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  description = "Environment variable name to short Secret Manager id."
  type        = map(string)
  default     = {}
}

variable "enable_cloudsql" {
  type    = bool
  default = false
}

variable "cloudsql_connection_name" {
  type    = string
  default = ""
}

variable "lakehouse_bucket" {
  description = "Bucket the job writes Parquet to."
  type        = string
}

variable "cpu" {
  description = "16Gi of memory requires at least 4 CPU in Cloud Run."
  type        = string
  default     = "4"
}

variable "memory" {
  type    = string
  default = "16Gi"
}

variable "timeout" {
  type    = string
  default = "7200s"
}

variable "max_retries" {
  type    = number
  default = 1
}

variable "labels" {
  type    = map(string)
  default = {}
}
