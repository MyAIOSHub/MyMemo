.PHONY: api worker worker-start worker-stop worker-restart database lint ruff \
        start-all stop-all status clean-cache \
        docker-buildx-prepare docker-buildx-clean docker-buildx-reset \
        docker-push docker-push-latest docker-release docker-build-local tag

VERSION := $(shell grep -m1 version pyproject.toml | cut -d'"' -f2)
DOCKERHUB_IMAGE := myaioshub/mymemo
GHCR_IMAGE := ghcr.io/myaioshub/mymemo
PLATFORMS := linux/amd64,linux/arm64

# === Local runtime ===

database:
	docker compose up -d surrealdb

api:
	uv run --env-file .env run_api.py

worker: worker-start

worker-start:
	@echo "Starting surreal-commands worker..."
	uv run --env-file .env surreal-commands-worker --import-modules commands

worker-stop:
	@echo "Stopping surreal-commands worker..."
	pkill -f "surreal-commands-worker" || true

worker-restart: worker-stop
	@sleep 2
	@$(MAKE) worker-start

start-all:
	@echo "Starting MyMemo backend (SurrealDB + API + Worker)..."
	@docker compose up -d surrealdb
	@sleep 3
	@uv run run_api.py &
	@sleep 2
	@uv run --env-file .env surreal-commands-worker --import-modules commands &
	@echo "API: http://localhost:5055"
	@echo "Docs: http://localhost:5055/docs"

stop-all:
	@pkill -f "surreal-commands-worker" || true
	@pkill -f "run_api.py" || true
	@pkill -f "uvicorn api.main:app" || true
	@docker compose down
	@echo "All services stopped."

status:
	@echo "SurrealDB:"
	@docker compose ps surrealdb 2>/dev/null || echo "  not running"
	@echo "API:"
	@pgrep -f "run_api.py\|uvicorn api.main:app" >/dev/null && echo "  running" || echo "  not running"
	@echo "Worker:"
	@pgrep -f "surreal-commands-worker" >/dev/null && echo "  running" || echo "  not running"

# === Linting ===

lint:
	uv run python -m mypy .

ruff:
	ruff check . --fix

# === Docker ===

docker-buildx-prepare:
	@docker buildx inspect multi-platform-builder >/dev/null 2>&1 || \
		docker buildx create --use --name multi-platform-builder --driver docker-container
	@docker buildx use multi-platform-builder

docker-buildx-clean:
	@docker buildx rm multi-platform-builder 2>/dev/null || true
	@docker ps -a | grep buildx_buildkit | awk '{print $$1}' | xargs -r docker rm -f 2>/dev/null || true

docker-buildx-reset: docker-buildx-clean docker-buildx-prepare

docker-build-local:
	docker build -t $(DOCKERHUB_IMAGE):$(VERSION) -t $(DOCKERHUB_IMAGE):local .

docker-push: docker-buildx-prepare
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-t $(DOCKERHUB_IMAGE):$(VERSION) \
		-t $(GHCR_IMAGE):$(VERSION) \
		--push .

docker-push-latest: docker-buildx-prepare
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-t $(DOCKERHUB_IMAGE):$(VERSION) \
		-t $(DOCKERHUB_IMAGE):v1-latest \
		-t $(GHCR_IMAGE):$(VERSION) \
		-t $(GHCR_IMAGE):v1-latest \
		--push .

docker-release: docker-push-latest

tag:
	@version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	echo "Creating tag v$$version"; \
	git tag "v$$version"; \
	git push origin "v$$version"

# === Cleanup ===

clean-cache:
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".mypy_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".ruff_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -type f -delete 2>/dev/null || true
