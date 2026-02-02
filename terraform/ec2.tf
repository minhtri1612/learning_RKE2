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
  count         = var.master_count
  ami           = local.ami_id
  instance_type = var.instance_type
  subnet_id     = aws_subnet.private_subnet_a.id
  vpc_security_group_ids = [
    aws_security_group.k8s_common_sg.id,
    aws_security_group.k8s_master_sg.id
  ]
  key_name                    = aws_key_pair.k8s_key.key_name
  iam_instance_profile        = aws_iam_instance_profile.k8s_profile.name
  associate_public_ip_address = false

  root_block_device {
    volume_size = 30 # 30GB for RKE2 + Rancher + ArgoCD + apps + buffer
    volume_type = "gp3"
  }

  # Spot instances for cost savings
  instance_market_options {
    market_type = "spot"
  }

  # User data để tự động cài đặt và cấu hình RKE2 Server
  user_data = <<-EOF
              #!/bin/bash
              set -e
              
              # ============================================
              # System Preparation (từ all.yaml)
              # ============================================
              
              # Disable swap temporarily
              swapoff -a || true
              
              # Disable swap permanently in fstab
              sed -i 's/^\([^#].*swap.*\)$/# \1 # Disabled for RKE2/' /etc/fstab || true
              
              # Load kernel modules
              modprobe overlay || true
              modprobe br_netfilter || true
              
              # Set sysctl params
              cat > /etc/sysctl.d/rke2.conf <<'SYSCTL'
              net.bridge.bridge-nf-call-iptables  = 1
              net.ipv4.ip_forward                 = 1
              SYSCTL
              sysctl --system || true
              
              # ============================================
              # RKE2 Server Installation
              # ============================================
              
              # Lấy private IP của instance này
              INSTANCE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
              
              # 1. Cài đặt RKE2 Server
              curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="server" sh -
              
              # 2. Tạo thư mục cấu hình
              mkdir -p /etc/rancher/rke2/
              
              # 3. Tạo file config.yaml
              cat <<EOT > /etc/rancher/rke2/config.yaml
              token: ${local.rke2_shared_token}
              write-kubeconfig-mode: "0644"
              tls-san:
                - "${aws_lb.k8s_master_nlb.dns_name}"
                - "$INSTANCE_IP"
              EOT
              
              # 4. Enable và start service
              systemctl enable rke2-server
              systemctl start rke2-server
              
              # 5. Đợi RKE2 server sẵn sàng (tối đa 5 phút)
              timeout 300 bash -c 'until systemctl is-active --quiet rke2-server && curl -k -s https://localhost:6443/readyz >/dev/null 2>&1; do sleep 5; done' || true
              
              # 6. Setup kubectl cho ubuntu user
              mkdir -p /home/ubuntu/.kube
              cp /etc/rancher/rke2/rke2.yaml /home/ubuntu/.kube/config
              chown -R ubuntu:ubuntu /home/ubuntu/.kube
              
              # 7. Add RKE2 bin to PATH và KUBECONFIG - SYSTEM-WIDE để tất cả users đều dùng được
              # Thêm vào /etc/profile.d để load khi login
              cat > /etc/profile.d/rke2.sh <<'PROFILE'
              export PATH=$PATH:/var/lib/rancher/rke2/bin
              # Nếu user có .kube/config thì dùng, không thì dùng system-wide
              if [ -f "$HOME/.kube/config" ]; then
                export KUBECONFIG="$HOME/.kube/config"
              elif [ -f "/etc/rancher/rke2/rke2.yaml" ]; then
                export KUBECONFIG="/etc/rancher/rke2/rke2.yaml"
              fi
              PROFILE
              chmod +x /etc/profile.d/rke2.sh
              
              # Tạo symlink vào /usr/local/bin để kubectl có thể dùng NGAY mà không cần PATH
              ln -sf /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/kubectl
              ln -sf /var/lib/rancher/rke2/bin/crictl /usr/local/bin/crictl
              ln -sf /var/lib/rancher/rke2/bin/ctr /usr/local/bin/ctr
              
              # Cũng thêm vào .bashrc của ubuntu user
              echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> /home/ubuntu/.bashrc
              
              # Setup kubeconfig cho root user (để sudo kubectl cũng work)
              mkdir -p /root/.kube
              cp /etc/rancher/rke2/rke2.yaml /root/.kube/config
              
              # Setup kubeconfig cho tất cả users có thể dùng (system-wide)
              # Tạo symlink hoặc copy vào /etc để mọi user đều có thể dùng
              mkdir -p /etc/rancher/rke2/kubeconfig
              cp /etc/rancher/rke2/rke2.yaml /etc/rancher/rke2/kubeconfig/config
              
              # Export PATH ngay trong session hiện tại (cho user_data script)
              export PATH=$PATH:/var/lib/rancher/rke2/bin
              EOF

  tags = { Name = "k8s-master-${count.index + 1}" }

  # Đảm bảo NLB đã được tạo trước khi tạo master instance
  depends_on = [aws_lb.k8s_master_nlb]
}

resource "aws_instance" "workers" {
  count         = var.worker_count
  ami           = local.ami_id
  instance_type = var.instance_type
  subnet_id     = element([aws_subnet.private_subnet_a.id, aws_subnet.private_subnet_b.id], count.index)
  vpc_security_group_ids = [
    aws_security_group.k8s_common_sg.id,
    aws_security_group.k8s_worker_sg.id
  ]
  key_name                    = aws_key_pair.k8s_key.key_name
  iam_instance_profile        = aws_iam_instance_profile.k8s_profile.name
  associate_public_ip_address = false

  root_block_device {
    volume_size = 30 # 30GB for RKE2 + Rancher + ArgoCD + apps + buffer
    volume_type = "gp3"
  }

  # Spot instances for cost savings
  instance_market_options {
    market_type = "spot"
  }

  # User data để tự động cài đặt và cấu hình RKE2 Agent
  user_data = <<-EOF
              #!/bin/bash
              set -e
              
              # ============================================
              # System Preparation (từ all.yaml)
              # ============================================
              
              # Disable swap temporarily
              swapoff -a || true
              
              # Disable swap permanently in fstab
              sed -i 's/^\([^#].*swap.*\)$/# \1 # Disabled for RKE2/' /etc/fstab || true
              
              # Load kernel modules
              modprobe overlay || true
              modprobe br_netfilter || true
              
              # Set sysctl params
              cat > /etc/sysctl.d/rke2.conf <<'SYSCTL'
              net.bridge.bridge-nf-call-iptables  = 1
              net.ipv4.ip_forward                 = 1
              SYSCTL
              sysctl --system || true
              
              # ============================================
              # RKE2 Agent Installation
              # ============================================
              
              # 1. Đợi Master node sẵn sàng (tối đa 10 phút)
              MASTER_IP="${aws_instance.masters[0].private_ip}"
              echo "Waiting for master node at $MASTER_IP:9345 to be ready..."
              timeout 600 bash -c 'until curl -k -s https://$MASTER_IP:9345 >/dev/null 2>&1 || nc -z $MASTER_IP 9345; do sleep 10; done' || true
              
              # 2. Cài đặt RKE2 Agent
              curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sh -
              
              # 3. Tạo thư mục cấu hình
              mkdir -p /etc/rancher/rke2/
              
              # 4. Tạo file config.yaml trỏ về Master
              cat <<EOT > /etc/rancher/rke2/config.yaml
              server: https://${aws_instance.masters[0].private_ip}:9345
              token: ${local.rke2_shared_token}
              EOT
              
              # 5. Enable và start service
              systemctl enable rke2-agent
              systemctl start rke2-agent
              
              # 6. Đợi agent join thành công (tối đa 5 phút)
              timeout 300 bash -c 'until systemctl is-active --quiet rke2-agent; do sleep 5; done' || true
              EOF

  tags = { Name = "k8s-worker-${count.index + 1}" }

  # Đảm bảo Master node đã được tạo và sẵn sàng trước khi tạo worker
  depends_on = [aws_instance.masters]
}

# -----------------------
# OpenVPN Server (thay Bastion: VPN 10.8.0.0/24, push route 10.0.0.0/16)
# Chỉ cài gói; cấu hình PKI, server.conf, client .ovpn do Ansible đảm nhiệm.
# -----------------------
resource "aws_instance" "openvpn" {
  ami                         = local.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public_subnet_a.id
  vpc_security_group_ids      = [aws_security_group.openvpn_sg.id]
  key_name                    = aws_key_pair.k8s_key.key_name
  associate_public_ip_address = true
  source_dest_check           = false # Cần cho IP forwarding / NAT trả traffic về VPN client

  root_block_device {
    volume_size = 12
    volume_type = "gp3"
  }

  # Chỉ cài đặt; setup OpenVPN (PKI, server.conf, iptables, .ovpn) chạy qua Ansible
  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y openvpn easy-rsa
              EOF

  tags = { Name = "k8s-openvpn" }
}

# Elastic IP cho OpenVPN: IP không đổi khi instance recreate → .ovpn không cần refresh
resource "aws_eip" "openvpn" {
  instance = aws_instance.openvpn.id
  domain   = "vpc"
  tags     = { Name = "k8s-openvpn-eip" }
}

# -----------------------
# Network Load Balancer (for K8s masters)
# -----------------------
resource "aws_lb" "k8s_master_nlb" {
  name                             = "k8s-master-nlb"
  internal                         = true
  load_balancer_type               = "network"
  subnets                          = [aws_subnet.public_subnet_a.id, aws_subnet.public_subnet_b.id]
  enable_cross_zone_load_balancing = true
  # Lưu ý: NLB không hỗ trợ security groups trực tiếp
  # Security được kiểm soát ở level của target instances (master nodes)

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

# -----------------------
# Application Load Balancer (for Web Applications)
# -----------------------
resource "aws_lb" "web_alb" {
  name               = "k8s-web-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.web_alb_sg.id]
  subnets            = [aws_subnet.public_subnet_a.id, aws_subnet.public_subnet_b.id]

  tags = {
    Name = "k8s-web-alb"
  }
}

# Target Group for HTTP traffic (port 80)
resource "aws_lb_target_group" "web_http_tg" {
  name        = "k8s-web-http-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.k8s_vpc.id
  target_type = "instance"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200,404"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  tags = {
    Name = "k8s-web-http-tg"
  }
}

# Target Group for HTTPS traffic (port 443)
resource "aws_lb_target_group" "web_https_tg" {
  name        = "k8s-web-https-tg"
  port        = 443
  protocol    = "HTTPS"
  vpc_id      = aws_vpc.k8s_vpc.id
  target_type = "instance"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200,404"
    port                = "traffic-port"
    protocol            = "HTTPS"
  }

  tags = {
    Name = "k8s-web-https-tg"
  }
}

# Register all master and worker nodes with HTTP target group
resource "aws_lb_target_group_attachment" "web_http_masters" {
  count            = length(aws_instance.masters)
  target_group_arn = aws_lb_target_group.web_http_tg.arn
  target_id        = aws_instance.masters[count.index].id
  port             = 80
}

resource "aws_lb_target_group_attachment" "web_http_workers" {
  count            = length(aws_instance.workers)
  target_group_arn = aws_lb_target_group.web_http_tg.arn
  target_id        = aws_instance.workers[count.index].id
  port             = 80
}

# Register all master and worker nodes with HTTPS target group
resource "aws_lb_target_group_attachment" "web_https_masters" {
  count            = length(aws_instance.masters)
  target_group_arn = aws_lb_target_group.web_https_tg.arn
  target_id        = aws_instance.masters[count.index].id
  port             = 443
}

resource "aws_lb_target_group_attachment" "web_https_workers" {
  count            = length(aws_instance.workers)
  target_group_arn = aws_lb_target_group.web_https_tg.arn
  target_id        = aws_instance.workers[count.index].id
  port             = 443
}

# HTTP Listener (redirect to HTTPS)
resource "aws_lb_listener" "web_http_listener" {
  load_balancer_arn = aws_lb.web_alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS Listener (without SSL certificate for now - will use self-signed in K8s)
resource "aws_lb_listener" "web_https_listener" {
  load_balancer_arn = aws_lb.web_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = aws_acm_certificate.web_cert.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_https_tg.arn
  }
}

# -----------------------
# Self-signed SSL Certificate for ALB
# -----------------------
resource "tls_private_key" "web_cert_key" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "web_cert" {
  private_key_pem = tls_private_key.web_cert_key.private_key_pem

  subject {
    common_name  = "*.local"
    organization = "Meo Stationery"
  }

  dns_names = [
    "meo-stationery.local",
    "argocd.local",
    "rancher.local",
    "*.local"
  ]

  validity_period_hours = 8760 # 1 year

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "aws_acm_certificate" "web_cert" {
  private_key      = tls_private_key.web_cert_key.private_key_pem
  certificate_body = tls_self_signed_cert.web_cert.cert_pem

  tags = {
    Name = "k8s-web-cert"
  }
}
