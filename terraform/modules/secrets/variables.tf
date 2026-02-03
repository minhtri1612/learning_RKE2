variable "environment" {
  type = string
}

variable "project_name" {
  type = string
}

variable "secret_name_suffix" {
  type        = string
  default     = "rke2-token"
  description = "Suffix for Secrets Manager secret name"
}

variable "postgres_service_host" {
  type        = string
  default     = "postgres.database.svc.cluster.local"
  description = "Postgres service host for DATABASE_URL (K8s DNS)"
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
  description = "Suffix for app-credentials secret name (e.g. -v2 when old secret is scheduled for deletion)"
}
