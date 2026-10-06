output "landing_address" {
  description = "Where the landing is served, once deployed."
  value       = "https://${cloudflare_pages_project.landing.subdomain}"
}

output "video_host" {
  description = "The bucket's public host. NEXT_PUBLIC_VIDEO_URL is https://<this>/<object name>."
  value       = cloudflare_r2_managed_domain.media.domain
}
