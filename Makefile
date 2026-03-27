# Makefile updated for Base + Env Layout
.PHONY: render-all render-dev render-prod clean

render-all: render-dev render-prod

render-dev:
	@echo "==> Rendering Dev manifests..."
	@mkdir -p .manifest/dev/backend
	@helm template backend 1-platform-engine/generic-app \
		--namespace meo-stationery \
		-f 2-platform-guardrails/dev-baseline.yaml \
		-f 3-developer-workspace/base/be.yaml \
		-f 3-developer-workspace/env/dev.yaml > .manifest/dev/backend/manifest.yaml
	@mkdir -p .manifest/dev/database
	@helm template database 1-platform-engine/generic-app \
		--namespace database \
		-f 2-platform-guardrails/dev-baseline.yaml \
		-f 3-developer-workspace/base/db.yaml \
		-f 3-developer-workspace/env/dev.yaml > .manifest/dev/database/manifest.yaml
	@echo "✅ Done (Dev)!"

render-prod:
	@echo "==> Rendering Prod manifests..."
	@mkdir -p .manifest/prod/backend
	@helm template backend 1-platform-engine/generic-app \
		--namespace meo-stationery \
		-f 2-platform-guardrails/prod-baseline.yaml \
		-f 3-developer-workspace/base/be.yaml \
		-f 3-developer-workspace/env/prod.yaml > .manifest/prod/backend/manifest.yaml
	@mkdir -p .manifest/prod/database
	@helm template database 1-platform-engine/generic-app \
		--namespace database \
		-f 2-platform-guardrails/prod-baseline.yaml \
		-f 3-developer-workspace/base/db.yaml \
		-f 3-developer-workspace/env/prod.yaml > .manifest/prod/database/manifest.yaml
	@echo "✅ Done (Prod)!"

clean:
	@echo "==> Cleaning up .manifest folder..."
	@rm -rf .manifest/*
	@echo "✅ Done!"
