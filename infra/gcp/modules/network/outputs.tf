output "network_id" {
  value = google_compute_network.vpc.id
}

output "network_name" {
  value = google_compute_network.vpc.name
}

output "subnetwork_name" {
  value = google_compute_subnetwork.app.name
}

output "subnetwork_id" {
  value = google_compute_subnetwork.app.id
}
