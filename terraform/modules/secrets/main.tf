# RKE2 token: tạo bằng Terraform, lưu trong AWS Secrets Manager (không cần tfvars)

resource "random_password" "rke2_token" {
  length  = 32
  special = false
  # RKE2 token thường alphanumeric
}

resource "aws_secretsmanager_secret" "rke2_token" {
  name                    = "${var.project_name}/${var.environment}/${var.secret_name_suffix}"
  description             = "RKE2 cluster join token (managed by Terraform)"
  recovery_window_in_days  = 0  # destroy = xóa ngay, không giữ tên 7–30 ngày
}

resource "aws_secretsmanager_secret_version" "rke2_token" {
  secret_id     = aws_secretsmanager_secret.rke2_token.id
  secret_string = random_password.rke2_token.result
}

# -----------------------------------------------------------------------------
# App credentials (database + nextauth) – dùng cho External Secrets / Helm
# -----------------------------------------------------------------------------
resource "random_password" "postgres_password" {
  length  = 24
  special = true
}

resource "random_password" "nextauth_secret" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "app_credentials" {
  name                    = "${var.project_name}/${var.environment}/app-credentials${var.app_credentials_name_suffix}"
  description             = "App credentials: POSTGRES_*, DATABASE_URL, NEXTAUTH_SECRET (for External Secrets)"
  recovery_window_in_days = 0  # destroy = xóa ngay, không giữ tên 7–30 ngày
}

resource "aws_secretsmanager_secret_version" "app_credentials" {
  secret_id = aws_secretsmanager_secret.app_credentials.id
  secret_string = jsonencode({
    POSTGRES_USER     = var.postgres_user
    POSTGRES_PASSWORD = random_password.postgres_password.result
    POSTGRES_DB       = var.postgres_db
    DATABASE_URL     = "postgresql://${var.postgres_user}:${random_password.postgres_password.result}@${var.postgres_service_host}:5432/${var.postgres_db}?schema=public"
    NEXTAUTH_SECRET   = random_password.nextauth_secret.result
  })
}
