output "nlb_dns_name" {
  value       = aws_lb.k8s_master_nlb.dns_name
  description = "NLB DNS for Kubernetes API"
}

output "nlb_tg_arn" {
  value = aws_lb_target_group.k8s_master_tg.arn
}

output "web_alb_dns_name" {
  value       = aws_lb.web_alb.dns_name
  description = "ALB DNS for web apps"
}

output "web_http_tg_arn" {
  value = aws_lb_target_group.web_http.arn
}

output "web_https_tg_arn" {
  value = aws_lb_target_group.web_https.arn
}
