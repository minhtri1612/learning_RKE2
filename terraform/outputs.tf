output "master_public_ip" {
  value = [for w in aws_instance.masters : w.public_ip]
}

output "worker_public_ips" {
  value = [for w in aws_instance.workers : w.public_ip]
}

output "ssh_key_file" {
  value = local_file.private_key.filename
}

output "nlb_dns_name" {
  value       = aws_lb.k8s_master_nlb.dns_name
  description = "NLB DNS name to use as the Kubernetes API endpoint"
}
