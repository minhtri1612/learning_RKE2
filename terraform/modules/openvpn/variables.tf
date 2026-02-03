variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "ami_id" {
  type        = string
  description = "AMI for OpenVPN (Ubuntu)"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "subnet_id" {
  type = string
}

variable "security_group_ids" {
  type = list(string)
}

variable "key_name" {
  type = string
}

variable "root_volume_size" {
  type    = number
  default = 12
}
