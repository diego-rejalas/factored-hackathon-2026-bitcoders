output "instance_name" {
  value = google_sql_database_instance.postgres.name
}

output "connection_name" {
  description = "project:region:instance, used by the Cloud SQL connector."
  value       = google_sql_database_instance.postgres.connection_name
}

output "public_ip" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "database_name" {
  value = google_sql_database.data.name
}

output "user_name" {
  value = google_sql_user.app.name
}

output "password" {
  value     = random_password.db.result
  sensitive = true
}

output "private_ip" {
  value = google_sql_database_instance.postgres.private_ip_address
}

output "extra_passwords" {
  description = "Password of each extra database's user, by database name."
  value       = { for name, password in random_password.extra : name => password.result }
  sensitive   = true
}
