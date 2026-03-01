# -----------------------------------------------------------------------------
# Outputs for Docker host module – dùng cho DockerHost CRD và ALB target attachment
# -----------------------------------------------------------------------------

output "instance_ids" {
  value       = aws_instance.docker_host[*].id
  description = "EC2 instance IDs (for ALB target group attachment)"
}

output "private_ips" {
  value       = aws_instance.docker_host[*].private_ip
  description = "Private IPs of Docker hosts (for DockerHost CRD hostURL: tcp://<ip>:2376)"
}

output "private_ip_by_index" {
  value       = { for i, inst in aws_instance.docker_host : tostring(i) => inst.private_ip }
  description = "Map of instance index to private IP (optional, for deterministic DockerHost naming)"
}
