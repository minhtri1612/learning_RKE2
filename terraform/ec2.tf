# -----------------------
# Generate SSH key
# -----------------------
resource "tls_private_key" "k8s_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "k8s_key" {
  key_name   = "k8s-key"
  public_key = tls_private_key.k8s_key.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.k8s_key.private_key_pem
  filename        = "${path.module}/k8s-key.pem"
  file_permission = "0600"
}

resource "aws_instance" "masters" {
  count                       = var.master_count
  ami                         = local.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public_subnet_a.id
  vpc_security_group_ids      = [
    aws_security_group.k8s_common_sg.id,
    aws_security_group.k8s_master_sg.id
  ]
  key_name                    = aws_key_pair.k8s_key.key_name
  iam_instance_profile        = aws_iam_instance_profile.k8s_profile.name
  associate_public_ip_address = true
  
  root_block_device {
    volume_size = 30  # 30GB for RKE2 + Rancher + ArgoCD + apps + buffer
    volume_type = "gp3"
  }
  
  # Spot instances for cost savings
  instance_market_options {
    market_type = "spot"
  }
  
  tags = { Name = "k8s-master-${count.index + 1}" }
}

resource "aws_instance" "workers" {
  count                       = var.worker_count
  ami                         = local.ami_id
  instance_type               = var.instance_type
  subnet_id                   = element([aws_subnet.public_subnet_a.id, aws_subnet.public_subnet_b.id], count.index)  
  vpc_security_group_ids      = [
    aws_security_group.k8s_common_sg.id,
    aws_security_group.k8s_worker_sg.id
  ]
  key_name                    = aws_key_pair.k8s_key.key_name
  iam_instance_profile        = aws_iam_instance_profile.k8s_profile.name
  associate_public_ip_address = true
  
  root_block_device {
    volume_size = 30  # 30GB for RKE2 + Rancher + ArgoCD + apps + buffer
    volume_type = "gp3"
  }
  
  # Spot instances for cost savings
  instance_market_options {
    market_type = "spot"
  }
  
  tags = { Name = "k8s-worker-${count.index + 1}" }
}

# -----------------------
# Network Load Balancer (for K8s masters)
# -----------------------
resource "aws_lb" "k8s_master_nlb" {
  name                             = "k8s-master-nlb"
  internal                         = false
  load_balancer_type               = "network"
  subnets                          = [aws_subnet.public_subnet_a.id, aws_subnet.public_subnet_b.id]
  enable_cross_zone_load_balancing = true

  tags = {
    Name = "k8s-master-nlb"
  }
}

# Target Group for API server (port 6443)
resource "aws_lb_target_group" "k8s_master_tg" {
  name        = "k8s-master-tg"
  port        = 6443
  protocol    = "TCP"
  vpc_id      = aws_vpc.k8s_vpc.id
  target_type = "instance"
  health_check {
    port                = "6443"
    protocol            = "TCP"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 10
  }

  tags = {
    Name = "k8s-master-tg"
  }
}

# Register all master nodes with the target group
resource "aws_lb_target_group_attachment" "k8s_master_attach" {
  count            = length(aws_instance.masters)
  target_group_arn = aws_lb_target_group.k8s_master_tg.arn
  target_id        = aws_instance.masters[count.index].id
  port             = 6443
}

# Listener for API Server
resource "aws_lb_listener" "k8s_master_listener" {
  load_balancer_arn = aws_lb.k8s_master_nlb.arn
  port              = 6443
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.k8s_master_tg.arn
  }
}
