CHART_DIR := 1-platform-engine/generic-app
MANIFEST_DIR := .manifest
TMP_DIR := .tmp/render
GUARDRAILS_BASE := 2-platform-guardrails/base/baseline.yaml
GUARDRAILS_ENV_DIR := 2-platform-guardrails/env
WORKSPACE_BASE_DIR := 3-developer-workspace/base
WORKSPACE_ENV_DIR := 3-developer-workspace/env

.PHONY: render-all render-dev render-staging render-prod clean

render-all: render-dev render-staging render-prod

render-dev:
	@$(MAKE) render ENV=dev

render-staging:
	@$(MAKE) render ENV=staging

render-prod:
	@$(MAKE) render ENV=prod

render:
	@echo "==> Rendering $(ENV) manifests..."
	@test -n "$(ENV)" || (echo "ENV is required"; exit 1)
	@test -f "$(GUARDRAILS_BASE)" || (echo "Missing $(GUARDRAILS_BASE)"; exit 1)
	@test -f "$(GUARDRAILS_ENV_DIR)/$(ENV).yaml" || (echo "Missing $(GUARDRAILS_ENV_DIR)/$(ENV).yaml"; exit 1)
	@test -f "$(WORKSPACE_ENV_DIR)/$(ENV).yaml" || (echo "Missing $(WORKSPACE_ENV_DIR)/$(ENV).yaml"; exit 1)
	@mkdir -p "$(TMP_DIR)/$(ENV)" "$(MANIFEST_DIR)/$(ENV)/backend" "$(MANIFEST_DIR)/$(ENV)/database"
	@yq eval '.backend' "$(WORKSPACE_ENV_DIR)/$(ENV).yaml" > "$(TMP_DIR)/$(ENV)/backend-env.yaml"
	@yq eval '.database' "$(WORKSPACE_ENV_DIR)/$(ENV).yaml" > "$(TMP_DIR)/$(ENV)/database-env.yaml"
	@helm template backend "$(CHART_DIR)" \
		--namespace meo-stationery \
		-f "$(GUARDRAILS_BASE)" \
		-f "$(GUARDRAILS_ENV_DIR)/$(ENV).yaml" \
		-f "$(WORKSPACE_BASE_DIR)/be.yaml" \
		-f "$(TMP_DIR)/$(ENV)/backend-env.yaml" \
		> "$(MANIFEST_DIR)/$(ENV)/backend/manifest.yaml"
	@helm template database "$(CHART_DIR)" \
		--namespace database \
		-f "$(GUARDRAILS_BASE)" \
		-f "$(GUARDRAILS_ENV_DIR)/$(ENV).yaml" \
		-f "$(WORKSPACE_BASE_DIR)/db.yaml" \
		-f "$(TMP_DIR)/$(ENV)/database-env.yaml" \
		> "$(MANIFEST_DIR)/$(ENV)/database/manifest.yaml"
	@echo "✅ Done ($(ENV))!"

clean:
	@echo "==> Cleaning rendered manifests and temp files..."
	@rm -rf "$(MANIFEST_DIR)"/* "$(TMP_DIR)"
	@echo "✅ Done!"
