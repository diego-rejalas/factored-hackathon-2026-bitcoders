variable "prefix" {
  description = "Prefix of every secret id (for example factored-dev)."
  type        = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "openrouter_api_key" {
  description = "Empty stores a placeholder; the agent then runs on deterministic replies."
  type        = string
  default     = ""
  sensitive   = true
}

variable "typesafe_api_key" {
  description = "Empty stores a placeholder; the agent then uses the LLM or keyword classifier."
  type        = string
  default     = ""
  sensitive   = true
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "enable_airflow" {
  description = "Create the secrets Airflow needs (metadata database password, Fernet key, API JWT secret, admin password)."
  type        = bool
  default     = false
}

variable "airflow_db_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "service_db_passwords" {
  description = "Password of each service's database role, by short name (backend, agent)."
  type        = map(string)
  default     = {}
  sensitive   = true
}
