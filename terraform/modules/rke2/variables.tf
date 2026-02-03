variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "ami_id" {
  type = string
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

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs (masters use first, workers spread)"
}

variable "k8s_common_sg_id" {
  type = string
}

variable "k8s_master_sg_id" {
  type = string
}

variable "k8s_worker_sg_id" {
  type = string
}

variable "iam_instance_profile_name" {
  type = string
}

variable "key_name" {
  type = string
}

variable "nlb_dns_name" {
  type        = string
  description = "NLB DNS for Kubernetes API (used in master user_data)"
}

variable "rke2_token" {
  type        = string
  description = "Shared token for RKE2 cluster"
  sensitive   = true
}

variable "root_volume_size" {
  type    = number
  default = 30
}

variable "use_spot_instances" {
  type    = bool
  default = true
}
