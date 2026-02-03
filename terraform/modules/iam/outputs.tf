output "instance_profile_name" {
  value = aws_iam_instance_profile.k8s.name
}

output "role_name" {
  value = aws_iam_role.k8s.name
}
