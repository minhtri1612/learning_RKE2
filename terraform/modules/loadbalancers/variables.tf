variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "web_alb_sg_id" {
  type = string
}

variable "alb_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for ALB HTTPS listener (self-signed or real)"
}
