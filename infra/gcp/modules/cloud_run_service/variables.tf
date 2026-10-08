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

variable "invoker_members" {
  description = "IAM members granted roles/run.invoker (for example the service account of the caller). Callers send an ID token."
  type        = list(string)
  default     = []
}

variable "ingress" {
  description = "Who can reach the service: INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (only through an external Application Load Balancer)."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
  validation {
    condition     = contains(["INGRESS_TRAFFIC_ALL", "INGRESS_TRAFFIC_INTERNAL_ONLY", "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"], var.ingress)
    error_message = "ingress must be INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER."
  }
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

variable "cpu_idle" {
  description = "Allocate the CPU only while a request is being served (request-based billing). Off keeps the CPU always allocated, which is billed for as long as an instance lives (a minimum instance, or the ~15 minutes after the last request). Work started after the response is paused until the next request."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "labels" {
  type    = map(string)
  default = {}
}
