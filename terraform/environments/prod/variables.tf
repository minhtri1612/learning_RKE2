# -----------------------------------------------------------------------------
# Prod environment variables (defaults hướng production: on-demand, thu hẹp my_ip)
# -----------------------------------------------------------------------------

variable "environment" {
  type    = string
  default = "prod"
}

variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "project_name" {
  type    = string
  default = "meo-stationery"
}

variable "my_ip" {
  description = "CIDR cho phép SSH vào OpenVPN (prod: nên set IP/VPN cụ thể, không dùng 0.0.0.0/0)"
  type        = string
  default     = ""
}

variable "ami_id" {
  type        = string
  description = "AMI override (để trống thì dùng Ubuntu 22.04 mới nhất)"
  default     = ""
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "master_count" {
  type    = number
  default = 1
}

variable "worker_count" {
  type    = number
  default = 2
}

variable "use_spot_instances" {
  type    = bool
  default = false
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}
