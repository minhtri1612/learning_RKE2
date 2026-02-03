variable "environment" {
  type        = string
  description = "Environment name"
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "project_name" {
  type        = string
  description = "Project name prefix (cho IAM policy ESO: secretsmanager GetSecretValue trên project_name/*)"
  default     = "meo-stationery"
}
