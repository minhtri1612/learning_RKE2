variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "project_name" {
  type    = string
  default = "meo-stationery"
}

variable "environments" {
  type        = set(string)
  description = "dev / staging / prod"
  default     = ["dev", "staging", "prod"]
}

variable "postgres_service_host" {
  type    = string
  default = "postgres.database.svc.cluster.local"
}

variable "postgres_user" {
  type    = string
  default = "meo_admin"
}

variable "postgres_db" {
  type    = string
  default = "meo_stationery"
}

variable "app_credentials_name_suffix_by_env" {
  type        = map(string)
  default     = {}
  description = "Ví dụ dev cần -v2: { \"dev\" = \"-v2\" }"
}

variable "eso_iam_user_suffix" {
  type        = string
  default     = "multi"
  description = "Hậu tố tên IAM user ESO (tránh trùng user tạo từ terraform/environments/*)"
}
