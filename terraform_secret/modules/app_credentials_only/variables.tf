variable "environment" {
  type = string
}

variable "project_name" {
  type = string
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

variable "app_credentials_name_suffix" {
  type        = string
  default     = ""
  description = "Hậu tố tên secret (vd: -v2)"
}
