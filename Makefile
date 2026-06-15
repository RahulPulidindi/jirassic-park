SHELL := /bin/bash
IMAGE := jirassic-park:latest
CONTAINER := jirassic-park
DATA_VOL := jirassic-data
PORT := 8080

# Computer-use demo: Anthropic's reference container that runs an Ubuntu desktop
# with Firefox, an agent loop, and a combined web UI at port 8080 (which we map
# to host port CU_PORT to avoid colliding with Jirassic Park itself on $(PORT)).
CU_CONTAINER := jp-computer-use
CU_IMAGE := ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
CU_PORT := 8081

.PHONY: help build run stop logs shell seed reset test demo mcp-demo agent-demo computer-use computer-use-stop computer-use-logs dev-backend dev-frontend clean

help:
	@echo "Jirassic Park - a Jira-like environment for humans and agents."
	@echo ""
	@echo "Container targets:"
	@echo "  make build        Build the Docker image"
	@echo "  make run          Run the container on port $(PORT) with persistent volume"
	@echo "  make stop         Stop and remove the running container"
	@echo "  make logs         Tail container logs"
	@echo "  make shell        Open a shell inside the running container"
	@echo "  make reset        Reset DB state to the seeded snapshot"
	@echo "  make seed         Rebuild the seed snapshot from fixtures"
	@echo "  make test         Run the backend test suite inside the container"
	@echo "  make demo         Run one of the seeded scenarios via the REST API"
	@echo "  make mcp-demo     Drive the MCP server end-to-end from a Python client"
	@echo "  make agent-demo   Let Claude drive the MCP to complete a real workflow"
	@echo "  make computer-use Start an Anthropic computer-use agent that drives the UI"
	@echo "  make clean        Remove container, image, and data volume"
	@echo ""
	@echo "Dev targets (no Docker):"
	@echo "  make dev-backend  Run uvicorn locally with the backend source"
	@echo "  make dev-frontend Run next dev locally"

build:
	docker build -t $(IMAGE) .

run: build
	-docker rm -f $(CONTAINER) >/dev/null 2>&1 || true
	docker run -d --name $(CONTAINER) -p $(PORT):8080 -v $(DATA_VOL):/data $(IMAGE)
	@echo "Jirassic Park running at http://localhost:$(PORT)"

stop:
	-docker rm -f $(CONTAINER) >/dev/null 2>&1 || true

logs:
	docker logs -f $(CONTAINER)

shell:
	docker exec -it $(CONTAINER) /bin/bash

reset:
	@curl -fsS -X POST http://localhost:$(PORT)/api/admin/reset \
		-H "Authorization: Bearer $${JP_ADMIN_TOKEN:-admin-token-jurassic}" | jq . || \
		docker exec $(CONTAINER) python -m app.seed.builder --reset

seed:
	docker exec $(CONTAINER) python -m app.seed.builder --rebuild

test:
	docker exec $(CONTAINER) pytest -q /app/backend/tests

demo:
	@bash backend/scripts/demo.sh || echo "Run 'make run' first"

mcp-demo:
	@if ! docker ps --format '{{.Names}}' | grep -q "^$(CONTAINER)$$"; then \
		echo "Container '$(CONTAINER)' is not running. Try: make run"; exit 1; \
	fi
	@docker exec -e MCP_URL=http://localhost:8080/mcp/ \
		$(CONTAINER) python /app/backend/scripts/mcp_demo.py

agent-demo:
	@if ! docker ps --format '{{.Names}}' | grep -q "^$(CONTAINER)$$"; then \
		echo "Container '$(CONTAINER)' is not running. Try: make run"; exit 1; \
	fi
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ANTHROPIC_API_KEY is not set. Export it before running this target:"; \
		echo "    export ANTHROPIC_API_KEY=sk-ant-..."; \
		exit 1; \
	fi
	@docker exec \
		-e ANTHROPIC_API_KEY="$$ANTHROPIC_API_KEY" \
		-e MCP_URL=http://localhost:8080/mcp/ \
		-e AGENT_MODEL="$${AGENT_MODEL:-claude-sonnet-4-5}" \
		$(CONTAINER) python /app/backend/scripts/agent_demo.py

# Computer-use demo: spin up Anthropic's reference image alongside Jirassic Park.
# The agent's Firefox reaches Jirassic Park via host.docker.internal:$(PORT).
# We bind the agent's combined UI to host port $(CU_PORT) so it doesn't collide.
computer-use:
	@if ! docker ps --format '{{.Names}}' | grep -q "^$(CONTAINER)$$"; then \
		echo "Jirassic Park is not running. Try: make run"; exit 1; \
	fi
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "ANTHROPIC_API_KEY is not set. Export it before running this target:"; \
		echo "    export ANTHROPIC_API_KEY=sk-ant-..."; \
		exit 1; \
	fi
	-@docker rm -f $(CU_CONTAINER) >/dev/null 2>&1 || true
	@mkdir -p $$HOME/.anthropic
	@docker run -d --rm \
		--name $(CU_CONTAINER) \
		--add-host=host.docker.internal:host-gateway \
		-e ANTHROPIC_API_KEY="$$ANTHROPIC_API_KEY" \
		-v "$$HOME/.anthropic":/home/computeruse/.anthropic \
		-p $(CU_PORT):8080 \
		-p 8501:8501 \
		-p 6080:6080 \
		-p 5900:5900 \
		$(CU_IMAGE) >/dev/null
	@printf '\nComputer-use agent is starting (first run may take ~30s while the image downloads).\n\n'
	@printf '  Combined UI (agent desktop + chat):  http://localhost:$(CU_PORT)\n'
	@printf '  Streamlit chat only:                 http://localhost:8501\n'
	@printf '  noVNC viewer only:                   http://localhost:6080\n\n'
	@printf 'Next:\n'
	@printf '  1. Open  http://localhost:$(CU_PORT)  in your browser.\n'
	@printf '  2. Paste the task from  ops/computer-use-task.md  into the chat panel.\n'
	@printf '  3. Watch Firefox in the desktop panel as the agent operates the UI.\n'
	@printf '  4. When done:  make computer-use-stop\n\n'
	@printf 'Tail logs:  make computer-use-logs\n'

computer-use-stop:
	-@docker rm -f $(CU_CONTAINER) >/dev/null 2>&1 || true
	@echo "Computer-use agent stopped."

computer-use-logs:
	@docker logs -f $(CU_CONTAINER)

dev-backend:
	cd backend && DATA_DIR=$$PWD/.data uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

dev-frontend:
	cd frontend && npm install && npm run dev

clean: stop
	-docker rmi $(IMAGE) >/dev/null 2>&1 || true
	-docker volume rm $(DATA_VOL) >/dev/null 2>&1 || true
