variable "environment" {
  type = string
}

variable "dns_names" {
  type        = list(string)
  description = "DNS names for the certificate (e.g. *.local, meo-stationery.local)"
  default     = ["meo-stationery.local", "argocd.local", "rancher.local", "*.local"]
}
