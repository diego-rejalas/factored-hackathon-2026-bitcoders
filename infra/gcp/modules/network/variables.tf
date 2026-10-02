variable "prefix" {
  description = "Name prefix of the environment (for example factored-dev)."
  type        = string
}

variable "region" {
  type = string
}

variable "subnet_cidr" {
  description = "Range of the application subnet: Cloud Run Direct VPC egress interfaces and, later, the Airflow VM. At least a /26."
  type        = string
}

variable "private_service_cidr" {
  description = "Range reserved for Private Service Access (Cloud SQL private IP). A /24 is enough."
  type        = string
}

variable "enable_nat" {
  description = "Create a Cloud Router and Cloud NAT so instances without an external IP can reach the internet (needed by the Airflow VM)."
  type        = bool
  default     = false
}
