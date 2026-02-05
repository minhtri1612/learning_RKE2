variable "environment" {
  type        = string
  description = "Environment name (dev, prod)"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for resource names"
  default     = "k8s"
}

variable "ami_id" {
  type        = string
  description = "AMI ID for the OpenVPN instance"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for OpenVPN server"
  default     = "t3.micro"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID where OpenVPN instance will be launched"
}

variable "security_group_ids" {
  type        = list(string)
  description = "List of security group IDs for OpenVPN instance"
}

variable "key_name" {
  type        = string
  description = "EC2 Key Pair name for SSH access"
}

variable "iam_instance_profile" {
  type        = string
  description = "IAM instance profile name for OpenVPN instance"
  default     = ""
}

variable "root_volume_size" {
  type        = number
  description = "Root volume size in GB"
  default     = 20
}