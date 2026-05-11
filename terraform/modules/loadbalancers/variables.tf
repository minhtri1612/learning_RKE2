variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = "k8s"
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "web_nlb_sg_id" {
  type = string
}
