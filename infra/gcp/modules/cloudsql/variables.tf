variable "name" {
  description = "Instance name. Reused names stay reserved for about a week after deletion."
  type        = string
}

variable "region" {
  type = string
}

variable "database_version" {
  description = "Cloud SQL engine version, for example POSTGRES_18. Raising it later is an in-place major upgrade with downtime."
  type        = string
  default     = "POSTGRES_18"
}

variable "tier" {
  description = "Machine tier, for example db-f1-micro or db-custom-2-7680."
  type        = string
}

variable "disk_size_gb" {
  type    = number
  default = 20
}

variable "availability_type" {
  description = "ZONAL or REGIONAL (high availability, roughly double the cost)."
  type        = string
  default     = "ZONAL"
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "activation_policy" {
  description = "ALWAYS to run, NEVER to pause (see scripts/manage_db.sh)."
  type        = string
  default     = "ALWAYS"
}

variable "point_in_time_recovery" {
  type    = bool
  default = false
}

variable "authorized_networks" {
  description = <<-EOT
    CIDR ranges allowed to connect over the public IP. Leave empty when clients use the
    Cloud SQL connector (Cloud Run volume mount), which needs no network allow-list.
  EOT
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}

variable "database_name" {
  type    = string
  default = "data"
}

variable "user_name" {
  type    = string
  default = "app"
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "enable_public_ip" {
  description = "Give the instance a public IPv4. Off by default: callers that need it (dev) say so explicitly."
  type        = bool
  default     = false
}

variable "private_ip" {
  description = "Attach the instance to private_network over Private Service Access."
  type        = bool
  default     = false
}

variable "private_network_id" {
  description = "VPC id for the private IP. Only used when private_ip is true."
  type        = string
  default     = ""
}

variable "extra_databases" {
  description = "Additional databases on the same instance, as { database = owner user }. Each gets its own generated password. Used for Airflow's metadata, kept apart from the business data."
  type        = map(string)
  default     = {}
}

variable "require_ssl" {
  description = "Refuse connections that are not encrypted (ssl_mode ENCRYPTED_ONLY). The clients here use sslmode=prefer, which negotiates TLS."
  type        = bool
  default     = true
}

variable "audit_logging" {
  description = <<-EOT
    Log connections, disconnections, lock waits, checkpoints, temporary files and DDL statements.
    Not enabled: log_duration and log_hostname (volume and reverse DNS cost) and pgaudit (the extension
    must also be created in the database); see .checkov.yaml.
  EOT
  type        = bool
  default     = false
}

variable "service_users" {
  description = "Login roles for the services that use the database, by short name (for example backend = \"backend_app\"). Each gets a generated password. The privileges are granted by infra/gcp/sql/roles.sql: Cloud SQL adds every user it creates to cloudsqlsuperuser, which that script removes."
  type        = map(string)
  default     = {}
}
