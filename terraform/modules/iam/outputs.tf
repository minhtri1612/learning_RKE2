output "instance_profile_name" {
  value = aws_iam_instance_profile.k8s.name
}

output "role_name" {
  value = aws_iam_role.k8s.name
}

output "eso_access_key_id" {
  value       = aws_iam_access_key.eso.id
  description = "Access key cho External Secrets Operator (deploy.py dùng để tạo K8s Secret aws-secrets-credentials)"
}

output "eso_secret_access_key" {
  value       = aws_iam_access_key.eso.secret
  sensitive   = true
  description = "Secret key cho ESO (chỉ dùng trong deploy.py, không in log)"
}
