resource "tls_private_key" "web" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "web" {
  private_key_pem = tls_private_key.web.private_key_pem

  subject {
    common_name  = "*.local"
    organization = "Meo Stationery"
  }

  dns_names             = var.dns_names
  validity_period_hours = 8760

  allowed_uses = ["key_encipherment", "digital_signature", "server_auth"]
}

resource "aws_acm_certificate" "web" {
  private_key       = tls_private_key.web.private_key_pem
  certificate_body  = tls_self_signed_cert.web.cert_pem

  tags = {
    Name = "k8s-web-cert-${var.environment}"
  }

  lifecycle {
    create_before_destroy = true
  }
}
