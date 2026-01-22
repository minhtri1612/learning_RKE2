resource "aws_vpc" "k8s_vpc" {
  cidr_block           = "10.0.0.0/16"  #10.0.0.0 → 10.0.255.255
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

# IGW = cầu nối giữa VPC và Internet
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.k8s_vpc.id
  tags   = { Name = "k8s-igw" }
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

# -----------------------
# Security Group
# -----------------------
resource "aws_security_group" "k8s_common_sg" {
  name        = "k8s-common-sg"
  vpc_id      = aws_vpc.k8s_vpc.id

  # SSH: Chỉ cho phép từ IP của bạn
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  # Giao tiếp nội bộ: Cho phép tất cả các nodes trong VPC giao tiếp với nhau
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


resource "aws_security_group" "k8s_master_sg" {
  name        = "k8s-master-sg"
  vpc_id      = aws_vpc.k8s_vpc.id

  # API Server: Cho phép từ nội bộ VPC (cho worker nodes và NLB health checks)
  # Đây là "bộ não" của toàn bộ Cluster. 
  # Mọi câu lệnh kubectl hoặc các yêu cầu từ Worker Node đều gửi về đây.
  ingress {
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  # API Server: Cho phép từ internet qua NLB
  # NLB preserve client IP, nên cần cho phép từ internet để kubectl có thể kết nối
  # Lưu ý: NLB sẽ forward traffic với source IP là client IP (từ internet)
  ingress {
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow Kubernetes API access via NLB from internet"
  }

  # RKE2 Supervisor: Chỉ cho phép từ nội bộ VPC để worker join vào
  # Nó dùng để các máy Worker "đăng ký" và tải các chứng chỉ bảo mật khi mới gia nhập vào Cluster.
  ingress {
    from_port   = 9345
    to_port     = 9345
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  # Kubelet API: Cho phép từ nội bộ VPC
  # Dùng để Master Node ra lệnh cho các Pod chạy trên chính nó hoặc để thu thập log/metrics.
  ingress {
    from_port   = 10250
    to_port     = 10250
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  # Flannel VXLAN: Cho phép từ nội bộ VPC
  # Đây là cổng dành cho mạng nội bộ của Kubernetes (CNI).
  # Flannel dùng để tạo ra một mạng ảo cho các Pods để chúng có thể giao tiếp với nhau.
  ingress {
    from_port   = 8472
    to_port     = 8472
    protocol    = "udp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  # HTTP/HTTPS: Cho phép từ internet để Ingress Controller có thể nhận traffic
  # Ingress Controller (nginx) chạy trên master node với hostPort 80/443
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTP traffic for Ingress Controller"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS traffic for Ingress Controller"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


resource "aws_security_group" "k8s_worker_sg" {
  name        = "k8s-worker-sg"
  vpc_id      = aws_vpc.k8s_vpc.id

  # HTTP/HTTPS: Mở cho mọi người truy cập ứng dụng web
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # Dùng để Master Node ra lệnh cho các Pod chạy trên chính nó hoặc để thu thập log/metrics.

  ingress {
    from_port   = 10250
    to_port     = 10250
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  # Flannel VXLAN: Cho phép từ nội bộ   
  # Đây là cổng dành cho mạng nội bộ của Kubernetes (CNI).
  # Flannel dùng để tạo ra một mạng ảo cho các Pods để chúng có thể giao tiếp với nhau.
  ingress {
    from_port   = 8472
    to_port     = 8472
    protocol    = "udp"
    cidr_blocks = [aws_vpc.k8s_vpc.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}