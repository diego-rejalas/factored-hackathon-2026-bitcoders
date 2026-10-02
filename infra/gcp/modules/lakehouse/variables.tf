variable "name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "location" {
  description = "Bucket location."
  type        = string
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a bucket that still holds objects."
  type        = bool
  default     = false
}

variable "nearline_after_days" {
  description = "Move objects to Nearline after this many days."
  type        = number
  default     = 30
}

variable "labels" {
  type    = map(string)
  default = {}
}
