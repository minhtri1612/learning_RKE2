output "master_private_ips" {
  value       = aws_instance.masters[*].private_ip
  description = "Private IPs of master nodes"
}

output "master_public_ips" {
  value = aws_instance.masters[*].public_ip
}

output "master_ids" {
  value       = aws_instance.masters[*].id
  description = "Instance IDs of masters (for NLB target group attachment)"
}

output "worker_ids" {
  value       = aws_instance.workers[*].id
  description = "Instance IDs of workers (for ALB target group attachment)"
}

output "worker_public_ips" {
  value = aws_instance.workers[*].public_ip
}
