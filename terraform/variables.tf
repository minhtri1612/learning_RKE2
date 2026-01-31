variable "region" {
  default = "ap-southeast-2"
}

variable "ami_id" {
  type    = string
  default = ""
}

variable "instance_type" {
  default = "t3.medium"
}

variable "my_ip" {
  description = "IP/CIDR cho phép SSH vào OpenVPN server (deploy / tạo client.ovpn). Mặc định 0.0.0.0/0. Nên thu hẹp cho production."
  type        = string
  default     = "0.0.0.0/0"
}

variable "master_count" {
  default = 1
}
variable "worker_count" {
  default = 2
}
