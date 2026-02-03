output "openvpn_public_ip" {
  value       = module.openvpn.openvpn_public_ip
  description = "Elastic IP OpenVPN – SSH: ssh -i k8s-key.pem ubuntu@<this-ip>"
}

output "master_private_ip" {
  value       = module.rke2.master_private_ips
  description = "Private IPs master nodes (sau khi VPN: ssh -i k8s-key.pem ubuntu@<ip>)"
}

output "master_public_ip" {
  value = module.rke2.master_public_ips
}

output "worker_public_ips" {
  value = module.rke2.worker_public_ips
}

output "nlb_dns_name" {
  value       = module.loadbalancers.nlb_dns_name
  description = "NLB DNS cho Kubernetes API"
}

output "web_alb_dns_name" {
  value       = module.loadbalancers.web_alb_dns_name
  description = "ALB DNS cho web (meo-stationery.local, argocd.local, rancher.local)"
}

output "ssh_key_file" {
  value       = module.keys.private_key_filename
  description = "Đường dẫn file private key (dùng cho deploy.py / kubectl)"
}

output "environment" {
  value = var.environment
}
