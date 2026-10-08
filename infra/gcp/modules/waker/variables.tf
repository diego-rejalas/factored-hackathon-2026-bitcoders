variable "name" {
  description = "Service name; also the base of the service account ids (30 characters or fewer)."
  type        = string
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image" {
  type = string
}

variable "sql_instance" {
  description = "Name of the Cloud SQL instance the waker stops and starts."
  type        = string
}

variable "watch_services" {
  description = "Cloud Run services whose traffic counts as someone using the demo."
  type        = list(string)
}

variable "airflow_vm" {
  description = "Name of the Airflow VM. While it runs the database never sleeps. Empty: no VM."
  type        = string
  default     = ""
}

variable "airflow_zone" {
  type    = string
  default = ""
}

variable "idle_minutes" {
  description = "Minutes without traffic before the database is stopped."
  type        = number
  default     = 30
}

variable "check_schedule" {
  description = "Cron expression (UTC) of the idle check."
  type        = string
  default     = "*/10 * * * *"
}

variable "cors_allowed_origins" {
  description = "Origins that may read the waker's answers from a browser (the landing). The page served by the load balancer is same-origin and needs none."
  type        = list(string)
  default     = []
}

variable "ingress" {
  type    = string
  default = "INGRESS_TRAFFIC_ALL"
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "labels" {
  type    = map(string)
  default = {}
}
