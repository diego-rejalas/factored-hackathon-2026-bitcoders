variable "name" {
  description = "Service name; also the service account id, so keep it at 30 characters or fewer."
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
  description = "Plain environment variables."
  type        = map(string)
  default     = {}
}

variable "secret_env" {
  description = "Environment variable name to short Secret Manager id (latest version is mounted)."
  type        = map(string)
  default     = {}
}

variable "enable_cloudsql" {
  description = "Mount the Cloud SQL connector and grant roles/cloudsql.client."
  type        = bool
  default     = false
}

variable "cloudsql_connection_name" {
  description = "project:region:instance. Only used when enable_cloudsql is true."
  type        = string
  default     = ""
}

variable "enable_vpc" {
  description = "Attach the workload to the VPC with Direct VPC egress (only private ranges go through it)."
  type        = bool
  default     = false
}

variable "vpc_network" {
  description = "VPC name. Only used when enable_vpc is true."
  type        = string
  default     = ""
}

variable "vpc_subnetwork" {
  description = "Subnetwork name. Only used when enable_vpc is true."
  type        = string
  default     = ""
}

variable "allow_unauthenticated" {
  description = "Grant roles/run.invoker to allUsers. Private services need callers that send an ID token."
  type        = bool
  default     = false
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 3
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "labels" {
  type    = map(string)
  default = {}
}
