# One VPC per environment. GCP subnets are regional and a VPC is global: "private" means no
# external IP, not a separate subnet type.

resource "google_compute_network" "vpc" {
  name                    = var.prefix
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

# Application subnet. Private Google Access lets instances without an external IP reach
# Google APIs (Artifact Registry, Secret Manager, Cloud Storage).
resource "google_compute_subnetwork" "app" {
  name                     = "${var.prefix}-app"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# Private Service Access: Google-managed services (Cloud SQL) get private IPs from this range.
resource "google_compute_global_address" "private_service_range" {
  name          = "${var.prefix}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = cidrhost(var.private_service_cidr, 0)
  prefix_length = tonumber(split("/", var.private_service_cidr)[1])
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]
  # Destroying the peering while a Cloud SQL instance still uses it fails; abandon it instead.
  deletion_policy = "ABANDON"
}

# Outbound internet for instances that have no external IP.
resource "google_compute_router" "this" {
  count   = var.enable_nat ? 1 : 0
  name    = "${var.prefix}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "this" {
  count                              = var.enable_nat ? 1 : 0
  name                               = "${var.prefix}-nat"
  region                             = var.region
  router                             = google_compute_router.this[0].name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Identity-Aware Proxy range: the only way in to instances tagged "iap" (SSH and the Airflow UI)
# without giving them an external IP.
resource "google_compute_firewall" "iap_ingress" {
  name      = "${var.prefix}-allow-iap"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["iap"]

  allow {
    protocol = "tcp"
    ports    = ["22", "8080"]
  }
}
