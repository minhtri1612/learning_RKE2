output "openvpn_public_ip" {
  value       = aws_instance.openvpn.public_ip
  description = "Public IP of OpenVPN Server - SSH: ssh -i terraform/k8s-key.pem ubuntu@<this-ip>"
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

output "web_alb_dns_name" {
  value       = aws_lb.web_alb.dns_name
  description = "ALB DNS name for web applications (meo-stationery.local, argocd.local, rancher.local)"
}

output "master_public_ip" {
  value       = [for m in aws_instance.masters : m.public_ip]
  description = "Public IPs of master nodes (for reference, they're in private subnets)"
}

output "master_private_ip" {
  value       = [for m in aws_instance.masters : m.private_ip]
  description = "Private IPs of master nodes (sau khi connect VPN: ssh -i terraform/k8s-key.pem ubuntu@<this-ip>)"
}
