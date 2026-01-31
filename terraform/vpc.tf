resource "aws_vpc" "k8s_vpc" {
  cidr_block           = "10.0.0.0/16" #10.0.0.0 → 10.0.255.255
  enable_dns_hostnames = true
  tags                 = { Name = "k8s-vpc" }
}

resource "aws_subnet" "public_subnet_a" {
  vpc_id            = aws_vpc.k8s_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = { Name = "k8s-public-a" }
}

resource "aws_subnet" "public_subnet_b" {
  vpc_id            = aws_vpc.k8s_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags              = { Name = "k8s-public-b" }
}

resource "aws_subnet" "private_subnet_a" {
  vpc_id            = aws_vpc.k8s_vpc.id
  cidr_block        = "10.0.101.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = { Name = "k8s-private-a" }
}

resource "aws_subnet" "private_subnet_b" {
  vpc_id            = aws_vpc.k8s_vpc.id
  cidr_block        = "10.0.102.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags              = { Name = "k8s-private-b" }
}

# IGW = cầu nối giữa VPC và Internet
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.k8s_vpc.id
  tags   = { Name = "k8s-igw" }
}

# Cần 1 Elastic IP cố định cho NAT Gateway
resource "aws_eip" "nat_eip" {
  domain = "vpc"
  tags   = { Name = "k8s-nat-eip" }
}

# NAT Gateway đặt tại Public Subnet
resource "aws_nat_gateway" "nat_gw" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = aws_subnet.public_subnet_a.id
  tags          = { Name = "k8s-nat-gw" }
}

# Route Table riêng cho Private Subnet
resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.k8s_vpc.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat_gw.id
  }

  # Reply path: traffic từ master/worker (private) về VPN client (10.8.0.0/24) phải đi qua OpenVPN instance
  route {
    cidr_block           = "10.8.0.0/24"
    network_interface_id = aws_instance.openvpn.primary_network_interface_id
  }

  tags = { Name = "k8s-private-rt" }
}

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.k8s_vpc.id
  tags   = { Name = "k8s-public-rt" }
}

# Mọi traffic không biết đi đâu → ra Internet
resource "aws_route" "default_route" {
  route_table_id         = aws_route_table.public_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.public_subnet_a.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_route_table_association" "b" {
  subnet_id      = aws_subnet.public_subnet_b.id
  route_table_id = aws_route_table.public_rt.id
}

# Liên kết Route Table này với các Private Subnets
resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_subnet_a.id
  route_table_id = aws_route_table.private_rt.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_subnet_b.id
  route_table_id = aws_route_table.private_rt.id
}

# -----------------------
# Security Group
# -----------------------

# OpenVPN Server: UDP 1194 từ internet, SSH từ my_ip (để deploy / tạo client config)
resource "aws_security_group" "openvpn_sg" {
  name        = "openvpn-sg"
  vpc_id      = aws_vpc.k8s_vpc.id
  description = "OpenVPN server + SSH for deploy"

  ingress {
    from_port   = 1194
    to_port     = 1194
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "OpenVPN from internet"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
    description = "SSH from deploy machine (Ansible / generate .ovpn)"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.8.0.0/24"]
    description = "SSH from VPN clients after connect"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "openvpn-sg" }
}

# Security Group chung cho K8s nodes
# SSH: từ OpenVPN server (jump cho deploy) VÀ từ VPN CIDR (user sau khi connect VPN)
resource "aws_security_group" "k8s_common_sg" {
  name   = "k8s-common-sg"
  vpc_id = aws_vpc.k8s_vpc.id

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.openvpn_sg.id]
    description     = "SSH from OpenVPN server (deploy jump)"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.8.0.0/24"]
    description = "SSH from VPN clients (10.8.0.0/24)"
  }

  ingress {
    from_port   = 8
    to_port     = 0
    protocol    = "icmp"
    cidr_blocks = ["10.8.0.0/24"]
    description = "Ping from VPN clients (no NAT)"
  }

  # Ping from OpenVPN server (traffic from VPN clients is MASQUERADEd to OpenVPN IP)
  ingress {
    from_port       = 8
    to_port         = 0
    protocol        = "icmp"
    security_groups = [aws_security_group.openvpn_sg.id]
    description     = "Ping from OpenVPN server (VPN client traffic after NAT)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "k8s-common-sg"
  }
}

# Security Group cho NLB đã được xóa
# Lưu ý: Network Load Balancer (NLB) KHÔNG hỗ trợ security groups trực tiếp
# Security được kiểm soát ở level của target instances (master nodes) qua k8s_master_sg
# NLB này là internal (internal = true) nên chỉ accessible từ trong VPC

# Security Group for Web Application Load Balancer
resource "aws_security_group" "web_alb_sg" {
  name        = "web-alb-sg"
  vpc_id      = aws_vpc.k8s_vpc.id
  description = "Security group for internet-facing ALB"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTP traffic from internet"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS traffic from internet"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "web-alb-sg"
  }
}


resource "aws_security_group" "k8s_master_sg" {
  name   = "k8s-master-sg"
  vpc_id = aws_vpc.k8s_vpc.id

  # API Server (6443):
  # - Private/Public subnets (workers, NLB)
  # - VPN CIDR 10.8.0.0/24 (user sau khi connect VPN có thể kubectl qua NLB hoặc direct)
  ingress {
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = [
      aws_subnet.private_subnet_a.cidr_block,
      aws_subnet.private_subnet_b.cidr_block,
      aws_subnet.public_subnet_a.cidr_block,
      aws_subnet.public_subnet_b.cidr_block,
      "10.8.0.0/24"
    ]
  }

  # RKE2 Supervisor: Chỉ cho phép từ Private Subnets để worker join vào
  ingress {
    from_port   = 9345
    to_port     = 9345
    protocol    = "tcp"
    cidr_blocks = [aws_subnet.private_subnet_a.cidr_block, aws_subnet.private_subnet_b.cidr_block]
  }

  # Kubelet API: Chỉ cho phép từ Private Subnets
  ingress {
    from_port   = 10250
    to_port     = 10250
    protocol    = "tcp"
    cidr_blocks = [aws_subnet.private_subnet_a.cidr_block, aws_subnet.private_subnet_b.cidr_block]
  }

  # Flannel VXLAN: Chỉ cho phép từ Private Subnets
  ingress {
    from_port   = 8472
    to_port     = 8472
    protocol    = "udp"
    cidr_blocks = [aws_subnet.private_subnet_a.cidr_block, aws_subnet.private_subnet_b.cidr_block]
  }

  # HTTP/HTTPS: ONLY allow from ALB (for external internet traffic)
  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.web_alb_sg.id]
    description     = "Allow HTTP traffic from ALB only"
  }

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.web_alb_sg.id]
    description     = "Allow HTTPS traffic from ALB only"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "k8s-master-sg"
  }
}


resource "aws_security_group" "k8s_worker_sg" {
  name   = "k8s-worker-sg"
  vpc_id = aws_vpc.k8s_vpc.id

  # HTTP/HTTPS: ONLY allow from ALB (for external internet traffic)
  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.web_alb_sg.id]
    description     = "Allow HTTP traffic from ALB only"
  }

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.web_alb_sg.id]
    description     = "Allow HTTPS traffic from ALB only"
  }

  # Kubelet API: Chỉ cho phép từ Private Subnets
  ingress {
    from_port   = 10250
    to_port     = 10250
    protocol    = "tcp"
    cidr_blocks = [aws_subnet.private_subnet_a.cidr_block, aws_subnet.private_subnet_b.cidr_block]
  }

  # Flannel VXLAN: Chỉ cho phép từ Private Subnets
  ingress {
    from_port   = 8472
    to_port     = 8472
    protocol    = "udp"
    cidr_blocks = [aws_subnet.private_subnet_a.cidr_block, aws_subnet.private_subnet_b.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "k8s-worker-sg"
  }
}