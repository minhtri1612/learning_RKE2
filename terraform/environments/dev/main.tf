# -----------------------------------------------------------------------------
# Dev environment – Docker host only (no RKE2). ALB/NLB vẫn có; NLB không còn target.
# Operator chạy trên Management; kết nối Docker daemon qua port 2376.
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
  source      = "../../modules/vpc"
  environment = var.environment
  name_prefix = var.name_prefix
  vpc_cidr    = var.vpc_cidr
  my_ip       = var.my_ip
  # Dev nằm VPC riêng (10.1.0.0/16)
  public_subnet_cidrs  = ["10.1.1.0/24", "10.1.2.0/24"]
  private_subnet_cidrs = ["10.1.101.0/24", "10.1.102.0/24"]
  # Cho phép VPC management (10.0.0.0/16) gọi API dev qua peering
  peer_vpc_cidrs = ["10.0.0.0/16"]
  # Cho phép Operator (Management) kết nối Docker daemon trên Docker host (port 2376)
  management_vpc_cidr = ["10.0.0.0/16"]
}

module "iam" {
  source       = "../../modules/iam"
  environment  = var.environment
  name_prefix  = var.name_prefix
  project_name = var.project_name
}

module "keys" {
  source       = "../../modules/keys"
  environment  = var.environment
  name_prefix  = var.name_prefix
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
  secret_name_suffix          = "rke2-token-v4" # v4 vì v3 đang scheduled for deletion trên AWS
  app_credentials_name_suffix = "-v2"           # v2 vì app-credentials cũ đang scheduled for deletion
}

module "loadbalancers" {
  source              = "../../modules/loadbalancers"
  environment         = var.environment
  name_prefix         = var.name_prefix
  vpc_id              = module.vpc.vpc_id
  public_subnet_ids   = module.vpc.public_subnet_ids
  web_alb_sg_id       = module.vpc.web_alb_sg_id
  alb_certificate_arn = module.certificate.certificate_arn
}

# OpenVPN chỉ có ở Management; dev truy cập qua VPC peering từ Management.

# Docker host – EC2 chỉ cài Docker, không RKE2. Operator (Management) điều khiển qua tcp://<ip>:2376.
module "docker_host" {
  source               = "../../modules/docker-host"
  name_prefix           = var.name_prefix
  environment           = var.environment
  instance_count        = var.worker_count
  instance_type         = var.instance_type
  ami_id                = local.ami_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  security_group_ids    = [module.vpc.k8s_common_sg_id, module.vpc.docker_host_sg_id]
  key_name              = module.keys.key_name
  docker_tcp_port       = 2376
}
