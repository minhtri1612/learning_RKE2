# OpenVPN chỉ có ở Management; dev truy cập qua jump host Management.

output "docker_host_private_ips" {
  value       = module.docker_host.private_ips
  description = "Private IPs của Docker host (cho DockerHost CRD hostURL; SSH qua VPN: ssh -i k8s-key.pem ubuntu@<ip>)"
}

output "docker_host_instance_ids" {
  value       = module.docker_host.instance_ids
  description = "EC2 instance IDs của Docker host (cho ALB target group attachment khi cần)"
}

output "master_private_ip" {
  value       = module.docker_host.private_ips
  description = "Deprecated: dùng docker_host_private_ips. Giữ để tương thích script cũ."
}

output "master_public_ip" {
  value       = []
  description = "Dev không còn RKE2; Docker host không public IP."
}

output "worker_public_ips" {
  value       = []
  description = "Dev không còn RKE2; Docker host không public IP."
}

output "nlb_dns_name" {
  value       = module.loadbalancers.nlb_dns_name
  description = "NLB DNS (Dev không còn K8s API; NLB không có target)"
}

output "cluster_api_url" {
  value       = null
  description = "Dev không có cluster; dùng cluster Management."
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

output "eso_access_key_id" {
  value       = module.iam.eso_access_key_id
  description = "ESO IAM access key (deploy.py dùng để tạo aws-secrets-credentials)"
}

output "eso_secret_access_key" {
  value       = module.iam.eso_secret_access_key
  sensitive   = true
  description = "ESO IAM secret key (deploy.py dùng, không in log)"
}
