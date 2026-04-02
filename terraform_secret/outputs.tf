output "app_credentials_secret_names" {
  value = {
    for env, m in module.app_credentials : env => m.app_credentials_secret_name
  }
  description = "Tên secret theo env → gán vào external-secrets values-* aws*SecretKey"
}

output "app_credentials_secret_arns" {
  value = {
    for env, m in module.app_credentials : env => m.app_credentials_secret_arn
  }
}

output "eso_iam_user_name" {
  value       = aws_iam_user.eso.name
  description = "IAM user để ESO dùng access key"
}

output "eso_access_key_id" {
  value       = aws_iam_access_key.eso.id
  sensitive   = true
  description = "Gán vào Secret aws-credentials key access-key-id"
}

output "eso_secret_access_key" {
  value       = aws_iam_access_key.eso.secret
  sensitive   = true
  description = "Gán vào Secret aws-credentials key secret-access-key"
}
