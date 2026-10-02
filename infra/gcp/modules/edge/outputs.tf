output "domain" {
  description = "Host name of the load balancer. It depends only on the reserved address, so the services behind it can use it in their own settings."
  value       = local.domain
}

output "ip_address" {
  value = google_compute_global_address.this.address
}

output "url" {
  value = "https://${local.domain}"
}
