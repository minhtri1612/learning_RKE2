output "app_credentials_secret_name" {
  value       = aws_secretsmanager_secret.app_credentials.name
  description = "Tên secret AWS (ExternalSecret remoteRef.key)"
}

output "app_credentials_secret_arn" {
  value       = aws_secretsmanager_secret.app_credentials.arn
  description = "ARN secret app-credentials"
}
