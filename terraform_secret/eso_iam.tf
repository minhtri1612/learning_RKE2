# IAM user cho External Secrets Operator: đọc Secrets Manager (prefix project).
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_user" "eso" {
  name = "${var.project_name}-eso-secrets-${var.eso_iam_user_suffix}"
  path = "/"
}

resource "aws_iam_user_policy" "eso_secrets_manager" {
  name   = "SecretsManagerGetSecretValue-${var.project_name}"
  user   = aws_iam_user.eso.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [
          "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*",
          "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:/${var.project_name}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_access_key" "eso" {
  user = aws_iam_user.eso.name
}
