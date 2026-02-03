resource "aws_instance" "openvpn" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = var.security_group_ids
  key_name                    = var.key_name
  iam_instance_profile        = var.iam_instance_profile
  associate_public_ip_address = true
  source_dest_check           = false

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y openvpn easy-rsa
              EOF

  tags = { Name = "${var.name_prefix}-openvpn-${var.environment}" }
}

resource "aws_eip" "openvpn" {
  instance = aws_instance.openvpn.id
  domain   = "vpc"
  tags     = { Name = "${var.name_prefix}-openvpn-eip-${var.environment}" }
}
