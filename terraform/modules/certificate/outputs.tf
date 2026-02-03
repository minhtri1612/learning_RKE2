output "certificate_arn" {
  value       = aws_acm_certificate.web.arn
  description = "ACM certificate ARN for ALB HTTPS listener"
}
