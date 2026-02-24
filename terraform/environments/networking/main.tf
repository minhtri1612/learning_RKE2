// VPC peering: management <-> dev, management <-> prod
// Chạy:
//   terraform -chdir=environments/networking init
//   terraform -chdir=environments/networking apply
// Prod VPC là optional — nếu chưa tạo thì peering prod sẽ bị skip.

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-southeast-2"
}

// Lấy 3 VPC theo tag Name (tạo trong module vpc)
data "aws_vpc" "management" {
  filter {
    name   = "tag:Name"
    values = ["k8s-vpc-management"]
  }
}

data "aws_vpc" "dev" {
  filter {
    name   = "tag:Name"
    values = ["k8s-vpc-dev"]
  }
}

// Dùng plural (aws_vpcs) để prod optional — không lỗi nếu chưa tạo
data "aws_vpcs" "prod" {
  filter {
    name   = "tag:Name"
    values = ["k8s-vpc-prod"]
  }
}

locals {
  prod_vpc_id = length(data.aws_vpcs.prod.ids) > 0 ? data.aws_vpcs.prod.ids[0] : null
}

// Peering management <-> dev
resource "aws_vpc_peering_connection" "mgmt_dev" {
  vpc_id      = data.aws_vpc.management.id
  peer_vpc_id = data.aws_vpc.dev.id
  auto_accept = true

  tags = {
    Name = "mgmt-dev-peering"
  }
}

// Peering management <-> prod (skip nếu prod chưa tạo)
resource "aws_vpc_peering_connection" "mgmt_prod" {
  count = local.prod_vpc_id != null ? 1 : 0

  vpc_id      = data.aws_vpc.management.id
  peer_vpc_id = local.prod_vpc_id
  auto_accept = true

  tags = {
    Name = "mgmt-prod-peering"
  }
}

// Route tables
data "aws_route_tables" "management_private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.management.id]
  }
  filter {
    name   = "tag:Name"
    values = ["k8s-private-rt-management"]
  }
}

// OpenVPN nằm ở public subnet → cần route peering trên public RT của management
data "aws_route_tables" "management_public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.management.id]
  }
  filter {
    name   = "tag:Name"
    values = ["k8s-public-rt-management"]
  }
}

data "aws_route_tables" "dev_private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.dev.id]
  }
  filter {
    name   = "tag:Name"
    values = ["k8s-private-rt-dev"]
  }
}

data "aws_route_tables" "prod_private" {
  count = local.prod_vpc_id != null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.prod_vpc_id]
  }
  filter {
    name   = "tag:Name"
    values = ["k8s-private-rt-prod"]
  }
}

locals {
  mgmt_rt_id     = length(data.aws_route_tables.management_private.ids) > 0 ? data.aws_route_tables.management_private.ids[0] : null
  mgmt_public_rt = length(data.aws_route_tables.management_public.ids) > 0 ? data.aws_route_tables.management_public.ids[0] : null
  dev_rt_id      = length(data.aws_route_tables.dev_private.ids) > 0 ? data.aws_route_tables.dev_private.ids[0] : null
  prod_rt_id     = local.prod_vpc_id != null && length(data.aws_route_tables.prod_private) > 0 && length(data.aws_route_tables.prod_private[0].ids) > 0 ? data.aws_route_tables.prod_private[0].ids[0] : null
}

// Routes management → dev
resource "aws_route" "mgmt_to_dev" {
  count                     = local.mgmt_rt_id != null ? 1 : 0
  route_table_id            = local.mgmt_rt_id
  destination_cidr_block    = "10.1.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_dev.id
}

// Routes management → prod (skip nếu prod chưa tạo)
resource "aws_route" "mgmt_to_prod" {
  count                     = local.mgmt_rt_id != null && local.prod_vpc_id != null ? 1 : 0
  route_table_id            = local.mgmt_rt_id
  destination_cidr_block    = "10.2.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_prod[0].id
}

// Route từ public subnet (OpenVPN) tới dev qua peering
resource "aws_route" "mgmt_public_to_dev" {
  count                     = local.mgmt_public_rt != null ? 1 : 0
  route_table_id            = local.mgmt_public_rt
  destination_cidr_block    = "10.1.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_dev.id
}

resource "aws_route" "mgmt_public_to_prod" {
  count                     = local.mgmt_public_rt != null && local.prod_vpc_id != null ? 1 : 0
  route_table_id            = local.mgmt_public_rt
  destination_cidr_block    = "10.2.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_prod[0].id
}

resource "aws_route" "dev_to_mgmt" {
  count                     = local.dev_rt_id != null ? 1 : 0
  route_table_id            = local.dev_rt_id
  destination_cidr_block    = "10.0.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_dev.id
}

resource "aws_route" "prod_to_mgmt" {
  count                     = local.prod_rt_id != null && local.prod_vpc_id != null ? 1 : 0
  route_table_id            = local.prod_rt_id
  destination_cidr_block    = "10.0.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.mgmt_prod[0].id
}
