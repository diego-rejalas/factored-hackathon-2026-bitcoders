# What the landing and the pitch need outside Google Cloud. It was created by hand first and then adopted into the state, so
# this is now the source of truth.

# The landing: a static export of site/, published with `wrangler pages deploy` (see site/README.md). Terraform owns the
# project; the files are deployed, not planned.
resource "cloudflare_pages_project" "landing" {
  account_id        = var.account_id
  name              = var.pages_project_name
  production_branch = var.production_branch
}

# The pitch video. Served from here and not from Pages because this answers range requests.
resource "cloudflare_r2_bucket" "media" {
  account_id = var.account_id
  name       = var.r2_bucket_name
}

# The bucket's public address (an r2.dev name). It is meant for development and Cloudflare rate-limits it: enough for the
# evaluation, not for a real audience. A custom domain on the bucket is the production answer.
resource "cloudflare_r2_managed_domain" "media" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.media.name
  enabled     = true
}

# The app's name, pointing at the Google Cloud load balancer. The proxy is off on purpose: with it on, the name would
# resolve to Cloudflare and Google could not issue the load balancer's certificate.
resource "cloudflare_dns_record" "app" {
  zone_id = var.zone_id
  name    = var.app_hostname
  type    = "A"
  content = var.edge_ip
  ttl     = 1 # automatic
  proxied = false
  comment = "Factored hackathon 2026, team bitcoders: LATAM Bank dispute assistant (GCP load balancer)"
}
