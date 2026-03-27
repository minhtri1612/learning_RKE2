# Mọi thao tác sinh manifest được gom lệnh vào đây cho nhàn

.PHONY: render-all render-dev render-prod clean

render-all: render-dev render-prod

render-dev:
	@echo "==> Rendering Dev manifests..."
	@mkdir -p .manifest/dev/backend
	@helm template backend 1-platform-engine/generic-app \
		--namespace meo-stationery \
		-f 2-platform-guardrails/dev-baseline.yaml \
		-f 3-developer-workspace/dev/backend.yaml > .manifest/dev/backend/manifest.yaml
	@mkdir -p .manifest/dev/database
	@helm template database 1-platform-engine/generic-app \
		--namespace database \
		-f 2-platform-guardrails/dev-baseline.yaml \
		-f 3-developer-workspace/dev/database.yaml > .manifest/dev/database/manifest.yaml
	@echo "✅ Done (Dev)!"

render-prod:
	@echo "==> Rendering Prod manifests..."
	@mkdir -p .manifest/prod/backend
	@helm template backend 1-platform-engine/generic-app \
		--namespace meo-stationery \
		-f 2-platform-guardrails/prod-baseline.yaml \
		-f 3-developer-workspace/prod/backend.yaml > .manifest/prod/backend/manifest.yaml
	@mkdir -p .manifest/prod/database
	@helm template database 1-platform-engine/generic-app \
		--namespace database \
		-f 2-platform-guardrails/prod-baseline.yaml \
		-f 3-developer-workspace/prod/database.yaml > .manifest/prod/database/manifest.yaml
	@echo "✅ Done (Prod)!"

clean:
	@echo "==> Cleaning up .manifest folder..."
	@rm -rf .manifest/*
	@echo "✅ Done!"
