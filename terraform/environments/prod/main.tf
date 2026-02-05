# -----------------------------------------------------------------------------
# Prod environment – RKE2 + OpenVPN + ALB/NLB
# Provider: symlink provider.tf -> ../../global/provider.tf (dùng chung)
# Chạy: terraform -chdir=environments/prod init && terraform -chdir=environments/prod apply -var-file=terraform.tfvars
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
  # Prod nằm VPC riêng (10.2.0.0/16)
  public_subnet_cidrs  = ["10.2.1.0/24", "10.2.2.0/24"]
  private_subnet_cidrs = ["10.2.101.0/24", "10.2.102.0/24"]
  # Cho phép VPC management (10.0.0.0/16) gọi API prod qua peering
  peer_vpc_cidrs       = ["10.0.0.0/16"]
}

module "iam" {
  source       = "../../modules/iam"
  environment  = var.environment
  name_prefix  = var.name_prefix
  project_name = var.project_name
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
  source       = "../../modules/secrets"
  environment  = var.environment
  project_name = var.project_name
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

# OpenVPN chỉ có ở Management; dev/prod truy cập qua VPC peering từ Management.

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
