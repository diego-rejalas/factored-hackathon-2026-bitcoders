output "frontend_uri" {
  value = module.frontend.uri
}

output "agent_uri" {
  value = module.agent.uri
}

output "backend_uri" {
  value = module.backend.uri
}

output "cloudsql_instance" {
  value = module.cloudsql.instance_name
}

output "cloudsql_connection_name" {
  value = module.cloudsql.connection_name
}

output "cloudsql_public_ip" {
  description = "Null when db_connectivity is private_ip."
  value       = module.cloudsql.public_ip
}

output "cloudsql_private_ip" {
  description = "Null when the instance has no private IP."
  value       = module.cloudsql.private_ip
}

output "network" {
  value = module.network.network_name
}

output "lakehouse_bucket" {
  description = "Bucket holding the bronze and silver Parquet."
  value       = module.lakehouse.name
}

output "etl_job" {
  value = module.etl.name
}

output "image_base" {
  description = "Registry path the CI pushes images to."
  value       = module.foundation.image_base
}

output "airflow_vm" {
  description = "Name of the Airflow VM, or null when Airflow is not enabled."
  value       = try(module.airflow[0].instance_name, null)
}

output "airflow_zone" {
  value = try(module.airflow[0].zone, null)
}

output "edge_url" {
  description = "Public HTTPS address of the application (load balancer). Null when the load balancer is off."
  value       = var.enable_edge ? module.edge[0].url : null
}

output "edge_locked" {
  description = "True when the frontend and the agent accept traffic only through the load balancer."
  value       = local.edge_locked
}
