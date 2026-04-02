# Một secret JSON trên AWS Secrets Manager cho External Secrets.
# Các key trong JSON (remoteRef.property):
#   POSTGRES User/Pass/DB, DATABASE_URL, NEXTAUTH_SECRET

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
  description             = "App credentials JSON for External Secrets (${var.environment})"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app_credentials" {
  secret_id = aws_secretsmanager_secret.app_credentials.id
  secret_string = jsonencode({
    POSTGRES_USER     = var.postgres_user
    POSTGRES_PASSWORD = random_password.postgres_password.result
    POSTGRES_DB       = var.postgres_db
    DATABASE_URL = "postgresql://${var.postgres_user}:${urlencode(random_password.postgres_password.result)}@${var.postgres_service_host}:5432/${var.postgres_db}?schema=public"
    NEXTAUTH_SECRET = random_password.nextauth_secret.result
  })
}
