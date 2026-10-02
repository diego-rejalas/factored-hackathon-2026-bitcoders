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
