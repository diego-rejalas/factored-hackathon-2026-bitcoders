variable "name" {
  description = "Prefix of every resource of the load balancer."
  type        = string
}

variable "project_id" {
  type = string
}

variable "region" {
  description = "Region of the Cloud Run services behind the load balancer."
  type        = string
}

variable "frontend_service" {
  description = "Name of the Cloud Run service that answers every path but /agent/."
  type        = string
}

variable "agent_service" {
  description = "Name of the Cloud Run service that answers /agent/*. The prefix is removed before the request reaches it."
  type        = string
}

variable "domain" {
  description = "Domain of the managed certificate. Empty: <ip>.sslip.io, a public DNS service that resolves any such name to its IP, so the certificate works without owning a domain."
  type        = string
  default     = ""
}

variable "rate_limit_per_minute" {
  description = "Requests per minute and client IP before Cloud Armor answers 429."
  type        = number
  default     = 300
}
