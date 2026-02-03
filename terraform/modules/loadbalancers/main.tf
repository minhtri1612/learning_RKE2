# NLB for K8s API (internal)
resource "aws_lb" "k8s_master_nlb" {
  name                             = "${var.name_prefix}-master-nlb-${var.environment}"
  internal                         = true
  load_balancer_type               = "network"
  subnets                          = var.public_subnet_ids
  enable_cross_zone_load_balancing  = true
  tags = { Name = "${var.name_prefix}-master-nlb-${var.environment}" }
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

# ALB for web apps
resource "aws_lb" "web_alb" {
  name               = "${var.name_prefix}-web-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.web_alb_sg_id]
  subnets            = var.public_subnet_ids
  tags               = { Name = "${var.name_prefix}-web-alb-${var.environment}" }
}

resource "aws_lb_target_group" "web_http" {
  name        = "${var.name_prefix}-web-http-tg-${var.environment}"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
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
  tags = { Name = "${var.name_prefix}-web-http-tg-${var.environment}" }
}

resource "aws_lb_target_group" "web_https" {
  name        = "${var.name_prefix}-web-https-tg-${var.environment}"
  port        = 443
  protocol    = "HTTPS"
  vpc_id      = var.vpc_id
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
  tags = { Name = "${var.name_prefix}-web-https-tg-${var.environment}" }
}

resource "aws_lb_listener" "web_http" {
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

resource "aws_lb_listener" "web_https" {
  load_balancer_arn = aws_lb.web_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.alb_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_https.arn
  }
}
