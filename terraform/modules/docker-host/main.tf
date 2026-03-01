# -----------------------------------------------------------------------------
# Docker host EC2 – chỉ cài Docker, không RKE2. Dùng cho Dev/Prod.
# Operator (chạy trên RKE2 Management) kết nối tới Docker daemon qua TCP.
# -----------------------------------------------------------------------------

resource "aws_instance" "docker_host" {
  count         = var.instance_count
  ami           = var.ami_id
  instance_type = var.instance_type
  subnet_id     = var.private_subnet_ids[count.index % length(var.private_subnet_ids)]
  vpc_security_group_ids = var.security_group_ids
  key_name               = var.key_name
  associate_public_ip_address = false

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/userdata_docker.sh", {
    docker_tcp_port = var.docker_tcp_port
  })
  user_data_replace_on_change = true

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.name_prefix}-docker-host-${count.index + 1}-${var.environment}"
  }
}
