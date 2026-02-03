locals {
  spot_options = var.use_spot_instances ? [{ market_type = "spot" }] : []
}

resource "aws_instance" "masters" {
  count         = var.master_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.private_subnet_ids[0]
  vpc_security_group_ids = [
    var.k8s_common_sg_id,
    var.k8s_master_sg_id
  ]
  key_name                    = var.key_name
  iam_instance_profile        = var.iam_instance_profile_name
  associate_public_ip_address = false

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  dynamic "instance_market_options" {
    for_each = local.spot_options
    content {
      market_type = "spot"
    }
  }

  user_data = templatefile("${path.module}/userdata_master.sh", {
    rke2_token = var.rke2_token
    nlb_dns    = var.nlb_dns_name
  })

  tags = { Name = "${var.name_prefix}-master-${count.index + 1}-${var.environment}" }
}

resource "aws_instance" "workers" {
  count         = var.worker_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.private_subnet_ids[count.index % length(var.private_subnet_ids)]
  vpc_security_group_ids = [
    var.k8s_common_sg_id,
    var.k8s_worker_sg_id
  ]
  key_name                    = var.key_name
  iam_instance_profile        = var.iam_instance_profile_name
  associate_public_ip_address = false

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  dynamic "instance_market_options" {
    for_each = local.spot_options
    content {
      market_type = "spot"
    }
  }

  user_data = templatefile("${path.module}/userdata_worker.sh", {
    rke2_token   = var.rke2_token
    master_ip    = aws_instance.masters[0].private_ip
  })

  tags = { Name = "${var.name_prefix}-worker-${count.index + 1}-${var.environment}" }
  depends_on = [aws_instance.masters]
}
