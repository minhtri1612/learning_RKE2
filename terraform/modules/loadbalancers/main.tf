# NLB for K8s API (internal)
resource "aws_lb" "k8s_master_nlb" {
  name                             = "${var.name_prefix}-master-nlb-${var.environment}"
  internal                         = true
  load_balancer_type               = "network"
  subnets                          = var.public_subnet_ids
  enable_cross_zone_load_balancing = true
  tags                             = { Name = "${var.name_prefix}-master-nlb-${var.environment}" }
}

resource "aws_lb_target_group" "k8s_master_tg" {
  name        = "${var.name_prefix}-master-tg-${var.environment}"
  port        = 6443
  protocol    = "TCP"
  vpc_id      = var.vpc_id
  target_type = "instance"
  health_check {
    port                = "6443"
    protocol            = "TCP"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 10
  }
  tags = { Name = "${var.name_prefix}-master-tg-${var.environment}" }
}

resource "aws_lb_listener" "k8s_master" {
  load_balancer_arn = aws_lb.k8s_master_nlb.arn
  port              = 6443
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.k8s_master_tg.arn
  }
}

# NLB for web apps
resource "aws_lb" "web_nlb" {
  name               = "${var.name_prefix}-web-nlb-${var.environment}"
  internal           = false
  load_balancer_type = "network"
  security_groups    = [var.web_nlb_sg_id]
  subnets            = var.public_subnet_ids
  tags               = { Name = "${var.name_prefix}-web-nlb-${var.environment}" }
}

resource "aws_lb_target_group" "web_http" {
  name        = "${var.name_prefix}-web-http-tg-${var.environment}"
  port        = 32080
  protocol    = "TCP"
  vpc_id      = var.vpc_id
  target_type = "instance"
  health_check {
    enabled             = true
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 10
    port                = "traffic-port"
    protocol            = "TCP"
  }
  tags = { Name = "${var.name_prefix}-web-http-tg-${var.environment}" }
}

resource "aws_lb_listener" "web_http" {
  load_balancer_arn = aws_lb.web_nlb.arn
  port              = "80"
  protocol          = "TCP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_http.arn
  }
}
