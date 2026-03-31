# ==============================================================================
# LOCAL TESTING MAKEFILE
# This Makefile is STRICTLY for local development and debugging.
# It simulates what ArgoCD does on the cluster to let you inspect the YAMLs.
# DO NOT COMMIT THE OUTPUT FILES TO GIT.
# ==============================================================================

ENV ?= dev
APP_DIR := app
ENV_DIR := env
TEMPLATE_DIR := template
TEST_OUT_DIR := .local-test-manifests

.PHONY: test check-env clean

check-env:
	@test -f "$(ENV_DIR)/$(ENV).yaml" || (echo "File $(ENV_DIR)/$(ENV).yaml does not exist!"; exit 1)

test: check-env clean
	@echo "=================================================="
	@echo "Testing K8s Manifest Generation for ENV: $(ENV)"
	@echo "=================================================="
	@mkdir -p $(TEST_OUT_DIR)/$(ENV)
	
	@# Parse top-level keys (services) from the environment file
	@SERVICES=$$(grep -E "^[a-zA-Z0-9_-]+:" $(ENV_DIR)/$(ENV).yaml | sed 's/://g'); \
	for svc in $$SERVICES; do \
		echo "=> Rendering Service: $$svc"; \
		PROFILE=$$(grep -A 5 "^$$svc:" $(ENV_DIR)/$(ENV).yaml | grep -m 1 "profile:" | awk '{print $$2}' | tr -d '"' | tr -d "'" || true); \
		if [ -z "$$PROFILE" ]; then \
			if [ "$$svc" = "database" ]; then \
				PROFILE="db"; \
			else \
				PROFILE="be"; \
			fi; \
		fi; \
		mkdir -p $(TEST_OUT_DIR)/$(ENV)/$$svc; \
		helm template $$svc $(TEMPLATE_DIR) \
			-f $(APP_DIR)/$$PROFILE.yaml \
			-f $(ENV_DIR)/$(ENV).yaml \
			--set currentService=$$svc \
			--set nameOverride=$$svc \
			> $(TEST_OUT_DIR)/$(ENV)/$$svc/manifest.yaml; \
		echo "   Saved: $(TEST_OUT_DIR)/$(ENV)/$$svc/manifest.yaml"; \
	done
	@echo "=================================================="
	@echo "✅ Done! You can inspect the $(TEST_OUT_DIR)/$(ENV) directory."

clean:
	@echo "==> Cleaning local test manifests..."
	@rm -rf $(TEST_OUT_DIR)
