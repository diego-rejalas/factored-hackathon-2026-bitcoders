# Nothing about the account, the zone or the names is written in the repository: the workflow reads every value from a
# repository variable, so the repository can be public.

variable "account_id" {
  description = "Id of the Cloudflare account that owns the Pages project and the bucket."
  type        = string
}

variable "zone_id" {
  description = "Id of the zone that holds the app's DNS record."
  type        = string
}

variable "app_hostname" {
  description = "Full DNS name of the app, inside the zone. It must point at the load balancer's address, without Cloudflare's proxy: Google issues the certificate by looking at where the name resolves."
  type        = string
}

variable "edge_ip" {
  description = "The load balancer's reserved address (the ip_address output of infra/gcp/envs/prod)."
  type        = string
}

variable "pages_project_name" {
  description = "Name of the Pages project that serves the landing. It is also the first part of its pages.dev address."
  type        = string
}

variable "production_branch" {
  description = "Branch whose deployments the Pages project treats as production."
  type        = string
  default     = "main"
}

variable "r2_bucket_name" {
  description = "Name of the bucket that holds the pitch video. The video lives here, not in the repository, because a bucket answers range requests and Pages does not, and a video that ignores them cannot be skipped through."
  type        = string
}
