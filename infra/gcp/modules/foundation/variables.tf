variable "region" {
  description = "Region of the Artifact Registry repository."
  type        = string
}

variable "prefix" {
  description = "Name prefix of the environment (for example factored-dev). Also the repository id."
  type        = string
}

variable "labels" {
  description = "Labels applied to the resources that support them."
  type        = map(string)
  default     = {}
}
