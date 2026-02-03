# -----------------------------------------------------------------------------
# Dev environment – RKE2 + OpenVPN + ALB/NLB
# Provider: symlink provider.tf -> ../../global/provider.tf (dùng chung)
# Chạy: terraform -chdir=environments/dev init && terraform -chdir=environments/dev apply -var-file=terraform.tfvars
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Data & locals
# -----------------------------------------------------------------------------
data "aws_availability_zones" "available" { state = "available" }

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu.id
}

# -----------------------------------------------------------------------------
# Modules
# -----------------------------------------------------------------------------
module "vpc" {
  source       = "../../modules/vpc"
  environment  = var.environment
  name_prefix  = var.name_prefix
  vpc_cidr     = var.vpc_cidr
  my_ip        = var.my_ip
}

module "iam" {
  source      = "../../modules/iam"
  environment = var.environment
  name_prefix = var.name_prefix
}

module "keys" {
  source      = "../../modules/keys"
  environment = var.environment
  name_prefix = var.name_prefix
  key_filename = "${path.module}/k8s-key.pem"
}

module "certificate" {
  source      = "../../modules/certificate"
  environment = var.environment
}

module "secrets" {
  source                      = "../../modules/secrets"
  environment                 = var.environment
  project_name                = var.project_name
  secret_name_suffix          = "rke2-token-v4"   # v4 vì v3 đang scheduled for deletion trên AWS
  app_credentials_name_suffix = "-v2"              # v2 vì app-credentials cũ đang scheduled for deletion
}

module "loadbalancers" {
  source               = "../../modules/loadbalancers"
  environment          = var.environment
  name_prefix          = var.name_prefix
  vpc_id               = module.vpc.vpc_id
  public_subnet_ids    = module.vpc.public_subnet_ids
  web_alb_sg_id        = module.vpc.web_alb_sg_id
  alb_certificate_arn  = module.certificate.certificate_arn
}

module "openvpn" {
  source             = "../../modules/openvpn"
  environment        = var.environment
  name_prefix        = var.name_prefix
  ami_id             = local.ami_id
  instance_type      = var.instance_type
  subnet_id          = module.vpc.public_subnet_a_id
  security_group_ids = [module.vpc.openvpn_sg_id]
  key_name           = module.keys.key_name
}

# Route: VPN reply path (traffic từ private subnet về 10.8.0.0/24 qua OpenVPN)
resource "aws_route" "vpn_reply" {
  route_table_id         = module.vpc.private_route_table_id
  destination_cidr_block = "10.8.0.0/24"
  network_interface_id    = module.openvpn.primary_network_interface_id
}

module "rke2" {
  source                    = "../../modules/rke2"
  environment               = var.environment
  name_prefix               = var.name_prefix
  ami_id                    = local.ami_id
  instance_type             = var.instance_type
  master_count              = var.master_count
  worker_count              = var.worker_count
  private_subnet_ids        = module.vpc.private_subnet_ids
  k8s_common_sg_id          = module.vpc.k8s_common_sg_id
  k8s_master_sg_id          = module.vpc.k8s_master_sg_id
  k8s_worker_sg_id          = module.vpc.k8s_worker_sg_id
  iam_instance_profile_name = module.iam.instance_profile_name
  key_name                  = module.keys.key_name
  nlb_dns_name              = module.loadbalancers.nlb_dns_name
  rke2_token                = module.secrets.rke2_token
  use_spot_instances        = var.use_spot_instances
}

# NLB target group attachment (masters)
resource "aws_lb_target_group_attachment" "nlb_masters" {
  count            = length(module.rke2.master_ids)
  target_group_arn = module.loadbalancers.nlb_tg_arn
  target_id        = module.rke2.master_ids[count.index]
  port             = 6443
}

# ALB target group attachments (masters + workers, HTTP + HTTPS)
resource "aws_lb_target_group_attachment" "web_http_masters" {
  count            = length(module.rke2.master_ids)
  target_group_arn = module.loadbalancers.web_http_tg_arn
  target_id        = module.rke2.master_ids[count.index]
  port             = 80
}
resource "aws_lb_target_group_attachment" "web_http_workers" {
  count            = length(module.rke2.worker_ids)
  target_group_arn = module.loadbalancers.web_http_tg_arn
  target_id        = module.rke2.worker_ids[count.index]
  port             = 80
}
resource "aws_lb_target_group_attachment" "web_https_masters" {
  count            = length(module.rke2.master_ids)
  target_group_arn = module.loadbalancers.web_https_tg_arn
  target_id        = module.rke2.master_ids[count.index]
  port             = 443
}
resource "aws_lb_target_group_attachment" "web_https_workers" {
  count            = length(module.rke2.worker_ids)
  target_group_arn = module.loadbalancers.web_https_tg_arn
  target_id        = module.rke2.worker_ids[count.index]
  port             = 443
}
