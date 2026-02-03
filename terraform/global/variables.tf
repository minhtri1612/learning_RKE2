# -----------------------------------------------------------------------------
# Global / shared variables (có thể override trong từng environment)
# -----------------------------------------------------------------------------

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

variable "environment" {
  description = "Environment name: dev, staging, prod"
  type        = string
}

variable "project_name" {
  description = "Project name prefix for resource tags"
  type        = string
  default     = "meo-stationery"
}
