variable "environment" {
  type        = string
  description = "Environment name (dev, prod)"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for resource names"
  default     = "k8s"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "VPC CIDR block"
}

variable "my_ip" {
  type        = string
  description = "CIDR cho phép SSH vào OpenVPN (ví dụ 0.0.0.0/0 hoặc IP/32)"
  default     = "0.0.0.0/0"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "peer_vpc_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDR các VPC peering (ví dụ VPC management) được phép truy cập API master (6443)."
}
