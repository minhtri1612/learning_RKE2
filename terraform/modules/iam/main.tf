resource "aws_iam_role" "k8s" {
  name = "${var.name_prefix}_role_${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.k8s.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_iam_instance_profile" "k8s" {
  name = "${var.name_prefix}_profile_${var.environment}"
  role = aws_iam_role.k8s.name
}

# -----------------------------------------------------------------------------
# IAM user cho External Secrets Operator (đọc AWS Secrets Manager → K8s Secret)
# deploy.py tạo K8s Secret aws-secrets-credentials từ Terraform output (eso_access_key_id, eso_secret_access_key)
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_user" "eso" {
  name = "${var.name_prefix}-eso-secrets-${var.environment}"
  path = "/"
}

resource "aws_iam_user_policy" "eso_secrets_manager" {
  name   = "SecretsManagerGetSecretValue"
  user   = aws_iam_user.eso.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
      }
    ]
  })
}

resource "aws_iam_access_key" "eso" {
  user = aws_iam_user.eso.name
}
