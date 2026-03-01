# -----------------------------------------------------------------------------
# Docker host module – EC2 chỉ cài Docker (không RKE2), dùng cho Dev/Prod
# K8s Docker Operator (Management) kết nối qua tcp://<private_ip>:docker_tcp_port
# -----------------------------------------------------------------------------

variable "name_prefix" {
  type        = string
  default     = "k8s"
  description = "Prefix for resource names"
}

variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod)"
}

variable "instance_count" {
  type        = number
  default     = 2
  description = "Number of Docker host EC2 instances"
}

variable "instance_type" {
  type        = string
  default     = "t2.small"
  description = "EC2 instance type (e.g. t2.small for cost savings)"
}

variable "ami_id" {
  type        = string
  description = "AMI ID for the instances (e.g. Ubuntu 22.04)"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs; instances are spread across these subnets"
}

variable "security_group_ids" {
  type        = list(string)
  description = "Security group IDs for the Docker host (e.g. k8s_common_sg + docker_host_sg)"
}

variable "key_name" {
  type        = string
  description = "SSH key pair name for EC2"
}

variable "docker_tcp_port" {
  type        = number
  default     = 2376
  description = "Port for Docker daemon TCP (2376 with TLS, 2375 without TLS). Operator connects to tcp://<private_ip>:<port>"
}

variable "root_volume_size" {
  type        = number
  default     = 20
  description = "Root EBS volume size in GB"
}
