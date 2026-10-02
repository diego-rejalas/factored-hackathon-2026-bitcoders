output "instance_name" {
  value = google_compute_instance.airflow.name
}

output "zone" {
  value = var.zone
}

output "private_ip" {
  value = google_compute_instance.airflow.network_interface[0].network_ip
}

output "service_account_email" {
  value = google_service_account.airflow.email
}
