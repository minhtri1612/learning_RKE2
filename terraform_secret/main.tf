module "app_credentials" {
  source   = "./modules/app_credentials_only"
  for_each = var.environments

  environment                 = each.key
  project_name                  = var.project_name
  postgres_service_host         = var.postgres_service_host
  postgres_user                 = var.postgres_user
  postgres_db                   = var.postgres_db
  app_credentials_name_suffix   = lookup(var.app_credentials_name_suffix_by_env, each.key, "")
}
