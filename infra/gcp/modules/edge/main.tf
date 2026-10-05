# External Application Load Balancer (global, EXTERNAL_MANAGED) in front of the public Cloud Run services:
#   /          -> frontend
#   /agent/*   -> agent (prefix removed)
# One HTTPS origin means the browser calls the agent on the same origin, so CORS does not apply. Cloud Armor
# filters both backends, and the services accept traffic only from this load balancer.

resource "google_compute_global_address" "this" {
  name    = "${var.name}-edge-ip"
  project = var.project_id
}

locals {
  domain = var.domain != "" ? var.domain : "${replace(google_compute_global_address.this.address, ".", "-")}.sslip.io"
  backends = {
    frontend = var.frontend_service
    agent    = var.agent_service
  }
}

resource "google_compute_managed_ssl_certificate" "this" {
  name    = "${var.name}-edge-cert-${substr(sha1(local.domain), 0, 6)}"
  project = var.project_id

  managed {
    domains = [local.domain]
  }

  # A certificate in use cannot be deleted: the new one is created first.
  lifecycle {
    create_before_destroy = true
  }
}

# One managed certificate per extra domain. Google issues each one once its DNS record points at the load balancer's
# address, which takes 15 to 60 minutes, and the main certificate keeps serving in the meantime.
resource "google_compute_managed_ssl_certificate" "additional" {
  for_each = toset(var.additional_domains)

  # The "add" in the name keeps it apart from the main certificate's name, so the same domain can be made the main one
  # later without the two resources fighting over one name.
  name    = "${var.name}-edge-cert-add-${substr(sha1(each.key), 0, 6)}"
  project = var.project_id

  managed {
    domains = [each.key]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Rules are evaluated by priority and the first match ends the evaluation. The WAF rules come first on purpose:
# the rate limit matches every request and its "conform" action is allow, so anything placed after it would
# never run.
resource "google_compute_security_policy" "this" {
  name        = "${var.name}-edge-policy"
  project     = var.project_id
  description = "Rate limit and the OWASP rules for SQL injection and cross-site scripting."

  rule {
    action   = "throttle"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_per_minute
        interval_sec = 60
      }
    }
    description = "Per-IP rate limit"
  }

  rule {
    action   = "deny(403)"
    priority = 100
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "SQL injection"
  }

  rule {
    action   = "deny(403)"
    priority = 101
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
    description = "Cross-site scripting"
  }

  rule {
    action   = "deny(403)"
    priority = 102
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('cve-canary')"
      }
    }
    description = "Known exploits, including Log4j (CVE-2021-44228)"
  }

  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default rule"
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}

resource "google_compute_region_network_endpoint_group" "this" {
  for_each              = local.backends
  name                  = "${var.name}-${each.key}-neg"
  project               = var.project_id
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = each.value
  }
}

resource "google_compute_backend_service" "this" {
  for_each              = local.backends
  name                  = "${var.name}-${each.key}-backend"
  project               = var.project_id
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.this.id

  backend {
    group = google_compute_region_network_endpoint_group.this[each.key].id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "https" {
  name            = "${var.name}-edge-https"
  project         = var.project_id
  default_service = google_compute_backend_service.this["frontend"].id

  host_rule {
    hosts        = ["*"]
    path_matcher = "app"
  }

  path_matcher {
    name            = "app"
    default_service = google_compute_backend_service.this["frontend"].id

    route_rules {
      priority = 1
      service  = google_compute_backend_service.this["agent"].id
      match_rules {
        prefix_match = "/agent/"
      }
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
  }
}

resource "google_compute_target_https_proxy" "this" {
  name             = "${var.name}-edge-https-proxy"
  project          = var.project_id
  url_map          = google_compute_url_map.https.id
  ssl_certificates = concat([google_compute_managed_ssl_certificate.this.id], [for c in google_compute_managed_ssl_certificate.additional : c.id])
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${var.name}-edge-https"
  project               = var.project_id
  ip_address            = google_compute_global_address.this.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.this.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# Port 80 only redirects to HTTPS.
resource "google_compute_url_map" "redirect" {
  name    = "${var.name}-edge-redirect"
  project = var.project_id

  default_url_redirect {
    https_redirect         = true
    strip_query            = false
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${var.name}-edge-http-proxy"
  project = var.project_id
  url_map = google_compute_url_map.redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${var.name}-edge-http"
  project               = var.project_id
  ip_address            = google_compute_global_address.this.id
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
