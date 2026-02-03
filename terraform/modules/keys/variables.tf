variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "key_filename" {
  type        = string
  description = "Path to write private key (relative to caller or absolute)"
  default     = "k8s-key.pem"
}
