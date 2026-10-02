variable "name" {
  description = "Instance name. Reused names stay reserved for about a week after deletion."
  type        = string
}

variable "region" {
  type = string
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
  description = "Give the instance a public IPv4. Set false together with private_ip."
  type        = bool
  default     = true
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
