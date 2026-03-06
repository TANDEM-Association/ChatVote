.PHONY: setup dev dev-infra dev-emulators dev-backend dev-frontend seed seed-firestore test-e2e check stop clean logs eval eval-static eval-e2e red-team generate-goldens optimize-prompts eval-report eval-report-static

# ---------------------------------------------------------------------------
# Setup — run once after cloning
# ---------------------------------------------------------------------------

setup:
	@echo "==> Creating .env files from templates (skipping if already present)..."
	@test -f CHATVOTE-BackEnd/.env \
		&& echo "     CHATVOTE-BackEnd/.env already exists — skipped" \
		|| (cp CHATVOTE-BackEnd/.env.local.template CHATVOTE-BackEnd/.env \
		    && echo "     Created CHATVOTE-BackEnd/.env")
	@test -f CHATVOTE-FrontEnd/.env.local \
		&& echo "     CHATVOTE-FrontEnd/.env.local already exists — skipped" \
		|| (cp CHATVOTE-FrontEnd/.env.local.template CHATVOTE-FrontEnd/.env.local \
		    && echo "     Created CHATVOTE-FrontEnd/.env.local")
	@echo ""
	@echo "==> Installing backend dependencies (Poetry)..."
	cd CHATVOTE-BackEnd && poetry install --with dev
	@echo ""
	@echo "==> Installing frontend dependencies (pnpm)..."
	cd CHATVOTE-FrontEnd && pnpm install --frozen-lockfile
	@echo ""
	@echo "==> Installing Firebase emulator tooling..."
	cd CHATVOTE-BackEnd/firebase && npm install
	@echo ""
	@echo "==> Setting up Ollama (LLM engine)..."
	@CHAT_MODEL=$$(grep -E '^OLLAMA_MODEL=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	EMBED_MODEL=$$(grep -E '^OLLAMA_EMBED_MODEL=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	CHAT_MODEL=$${CHAT_MODEL:-llama3.2}; \
	EMBED_MODEL=$${EMBED_MODEL:-nomic-embed-text}; \
	if command -v ollama > /dev/null 2>&1; then \
		echo "     Ollama is installed natively (GPU accelerated)."; \
		echo "     Pulling models (this may take a few minutes on first run)..."; \
		echo "     Chat: $$CHAT_MODEL, Embed: $$EMBED_MODEL"; \
		ollama pull $$CHAT_MODEL || true; \
		ollama pull $$EMBED_MODEL || true; \
	else \
		echo "     Ollama not found. For best performance on macOS, install natively:"; \
		echo "       brew install ollama && ollama serve"; \
		echo "     Otherwise, Docker will run Ollama on CPU (slower)."; \
	fi
	@echo ""
	@echo "Setup complete! Run 'make dev' to start all services."

# ---------------------------------------------------------------------------
# Development — start everything with a single command
# ---------------------------------------------------------------------------

dev: dev-infra
	@mkdir -p $(CURDIR)/.logs
	@echo "Seeding data..."
	@$(MAKE) seed
	@echo ""
	@echo "Starting backend (logs → .logs/backend.log)..."
	@cd CHATVOTE-BackEnd && \
		poetry run python -m src.aiohttp_app --debug \
		> $(CURDIR)/.logs/backend.log 2>&1 & \
		echo "$$!" > $(CURDIR)/.logs/backend.pid
	@echo "Starting frontend (logs → .logs/frontend.log)..."
	@cd CHATVOTE-FrontEnd && \
		npm run dev \
		> $(CURDIR)/.logs/frontend.log 2>&1 & \
		echo "$$!" > $(CURDIR)/.logs/frontend.pid
	@echo ""
	@echo "Waiting for services to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -sf http://localhost:8080/healthz > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -so /dev/null http://localhost:3000/chat 2>/dev/null; then \
			break; \
		fi; \
		sleep 1; \
	done
	@echo ""
	@echo "=== All services running ==="
	@echo ""
	@$(MAKE) check
	@echo ""
	@echo "  Qdrant dashboard:  http://localhost:6333/dashboard"
	@echo "  App:               http://localhost:3000"
	@echo ""
	@echo "  Logs:  make logs           (tail all logs)"
	@echo "  Stop:  make stop           (stop everything)"
	@echo ""

dev-infra:
	@PROFILES=""; \
	if curl -sf http://localhost:11434/ > /dev/null 2>&1; then \
		echo "Native Ollama detected on :11434 — skipping Docker Ollama (GPU accelerated)."; \
	elif command -v ollama > /dev/null 2>&1; then \
		echo "Native Ollama found but not serving — starting it..."; \
		ollama serve > .logs/ollama.log 2>&1 & \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			if curl -sf http://localhost:11434/ > /dev/null 2>&1; then break; fi; \
			sleep 1; \
		done; \
		if curl -sf http://localhost:11434/ > /dev/null 2>&1; then \
			echo "Native Ollama started on :11434 (GPU accelerated)."; \
		else \
			echo "Failed to start native Ollama — falling back to Docker (CPU only)."; \
			PROFILES="$$PROFILES --profile ollama"; \
		fi; \
	else \
		echo "No native Ollama found — starting Ollama in Docker (CPU only, slow on macOS)."; \
		echo "TIP: For Apple Silicon, install natively: brew install ollama && ollama serve"; \
		PROFILES="$$PROFILES --profile ollama"; \
	fi; \
	if curl -sf http://localhost:8081/ > /dev/null 2>&1; then \
		echo "Native Firebase emulators detected on :8081 — skipping Docker emulators."; \
	else \
		echo "No native Firebase emulators found — starting in Docker."; \
		PROFILES="$$PROFILES --profile firebase"; \
	fi; \
	docker compose -f docker-compose.dev.yml $$PROFILES up -d --wait

# Backward-compat alias — Firebase emulators now run inside Docker via dev-infra
dev-emulators: dev-infra

# ---------------------------------------------------------------------------
# Run a single service in the foreground (for debugging)
# ---------------------------------------------------------------------------

dev-backend:
	cd CHATVOTE-BackEnd && poetry run python -m src.aiohttp_app --debug

dev-frontend:
	cd CHATVOTE-FrontEnd && npm run dev

# ---------------------------------------------------------------------------
# Data seeding
# ---------------------------------------------------------------------------

seed:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py --with-vectors

seed-firestore:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py

test-e2e:
	@echo "Starting infrastructure..."
	@$(MAKE) dev-infra
	@echo "Waiting for services..."
	@for i in $$(seq 1 30); do \
		if curl -sf http://localhost:6333/healthz > /dev/null 2>&1 && \
		   curl -sf http://localhost:8081 > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 2; \
	done
	@echo "Seeding data..."
	@$(MAKE) seed
	@mkdir -p $(CURDIR)/.logs
	@echo "Starting backend..."
	@cd CHATVOTE-BackEnd && timeout 300 poetry run python -m src.aiohttp_app --debug \
		> $(CURDIR)/.logs/backend-test.log 2>&1 & echo $$! > $(CURDIR)/.logs/backend-test.pid
	@echo "Waiting for backend..."
	@for i in $$(seq 1 15); do \
		curl -sf http://localhost:8080/healthz > /dev/null 2>&1 && break; \
		sleep 2; \
	done
	@echo "Running Playwright tests..."
	@cd CHATVOTE-FrontEnd && npx playwright test --reporter=list
	@echo "Stopping backend..."
	@if [ -f $(CURDIR)/.logs/backend-test.pid ]; then \
		kill $$(cat $(CURDIR)/.logs/backend-test.pid) 2>/dev/null || true; \
		rm -f $(CURDIR)/.logs/backend-test.pid; \
	fi
	@$(MAKE) stop

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

check:
	@echo "Checking services..."
	@printf "  Qdrant    (:6333)  ... " && \
		(curl -sf http://localhost:6333/healthz > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Ollama    (:11434) ... " && \
		(curl -sf http://localhost:11434/ > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Firestore (:8081)  ... " && \
		(curl -sf http://localhost:8081/ > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Backend   (:8080)  ... " && \
		(curl -sf http://localhost:8080/healthz > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Frontend  (:3000)  ... " && \
		(curl -so /dev/null -w '' http://localhost:3000/chat 2>/dev/null && echo "OK" || echo "FAIL")

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

logs:
	@tail -f .logs/backend.log .logs/frontend.log

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

stop:
	@echo "Stopping all services..."
	docker compose -f docker-compose.dev.yml --profile ollama --profile firebase down
	@for svc in backend frontend; do \
		if [ -f .logs/$$svc.pid ]; then \
			kill $$(cat .logs/$$svc.pid) 2>/dev/null || true; \
			rm -f .logs/$$svc.pid; \
			echo "  $$svc stopped."; \
		fi; \
	done
	@echo "All services stopped."

# ---------------------------------------------------------------------------
# RAG Evaluation (DeepEval)
# ---------------------------------------------------------------------------

eval:
	cd CHATVOTE-BackEnd && poetry run deepeval test run tests/eval/ tests/red_team/ -v

eval-static:
	cd CHATVOTE-BackEnd && poetry run deepeval test run tests/eval/test_rag_generator.py tests/eval/test_custom_metrics.py tests/red_team/ -v -k "static or neutrality or attribution or completeness or french or refusal or injection or bias"

eval-e2e:
	cd CHATVOTE-BackEnd && poetry run deepeval test run tests/eval/test_rag_e2e.py tests/eval/test_rag_retriever.py -v

red-team:
	cd CHATVOTE-BackEnd && poetry run deepeval test run tests/red_team/ -v

generate-goldens:
	cd CHATVOTE-BackEnd && poetry run python scripts/generate_goldens.py

optimize-prompts:
	cd CHATVOTE-BackEnd && poetry run python scripts/optimize_prompts.py

eval-report:
	cd CHATVOTE-BackEnd && poetry run python scripts/eval_report.py --tests all

eval-report-static:
	cd CHATVOTE-BackEnd && poetry run python scripts/eval_report.py --tests static

clean: stop
	docker compose -f docker-compose.dev.yml --profile ollama --profile firebase down -v
