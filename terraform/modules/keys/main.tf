resource "tls_private_key" "k8s" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "k8s" {
  key_name   = "${var.name_prefix}-key-${var.environment}"
  public_key = tls_private_key.k8s.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.k8s.private_key_pem
  filename        = pathexpand(var.key_filename)
  file_permission = "0600"
}
