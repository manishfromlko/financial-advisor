# Convenience wrappers around the commands documented in README.md.
# Every target just calls `uv run ...` — nothing here is required, use the
# raw commands directly if you prefer.

.PHONY: install install-dev install-deploy run web test test-live eval lint \
        deploy-adk deploy-a2a update-adk update-a2a list-agents

install:       ## Install runtime dependencies
	uv sync

install-dev:   ## Install dev dependencies (tests, lint)
	uv sync --dev

install-deploy: ## Install deployment dependencies
	uv sync --group deployment

run:           ## Talk to the agent locally via the ADK CLI
	uv run adk run financial_advisor

web:           ## Talk to the agent locally via the ADK web UI
	uv run adk web

test:          ## Fast unit tests (no GCP calls)
	uv run pytest tests/unit

test-live:     ## Live tests against deployed Reasoning Engines (needs gcloud auth + resource IDs)
	uv run pytest -m live tests/live -v

eval:          ## ADK AgentEvaluator dataset
	uv run pytest eval

lint:          ## ruff + mypy
	uv run ruff check .
	uv run mypy financial_advisor

deploy-adk:    ## Create the ADK Agent Engine deployment
	uv run deployment/deploy.py --create

deploy-a2a:    ## Create the A2A Agent Engine deployment
	uv run deployment/deploy.py --create_a2a

update-adk:    ## Update the ADK deployment (requires RESOURCE_ID=...)
	uv run deployment/deploy.py --update --resource_id=$(RESOURCE_ID)

update-a2a:    ## Update the A2A deployment (requires RESOURCE_ID=...)
	uv run deployment/deploy.py --update_a2a --resource_id=$(RESOURCE_ID)

list-agents:   ## List deployed Agent Engine resources
	uv run deployment/deploy.py --list
