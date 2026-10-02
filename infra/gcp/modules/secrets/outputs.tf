output "secret_ids" {
  description = "Short secret ids by logical name (session-jwt, db-password, ...)."
  value       = { for name, secret in google_secret_manager_secret.this : name => secret.secret_id }
}
