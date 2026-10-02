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
  value = module.cloudsql.public_ip
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
