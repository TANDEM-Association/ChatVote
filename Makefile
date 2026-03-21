.PHONY: setup dev dev-infra dev-emulators dev-backend dev-frontend seed seed-local seed-qwen seed-snapshots seed-firestore seed-firestore-if-empty snapshot test-e2e check stop clean logs logs-prod logs-backend logs-frontend logs-qdrant logs-k8s check-prod eval eval-static eval-e2e red-team generate-goldens optimize-prompts eval-report eval-report-static

# ---------------------------------------------------------------------------
# Setup — run once after cloning
# ---------------------------------------------------------------------------

setup:
	@bash scripts/setup.sh
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
	@echo "==> Setting up LLM engine..."
	@PROVIDER=$$(grep -E '^EMBEDDING_PROVIDER=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	CHAT_MODEL=$$(grep -E '^OLLAMA_MODEL=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	CHAT_MODEL=$${CHAT_MODEL:-qwen3:32b}; \
	if [ "$$PROVIDER" = "scaleway" ]; then \
		echo "     Using Scaleway qwen for embeddings (cloud mode, 4096d)."; \
		echo "     Ollama chat model still needed for local LLM."; \
		if command -v ollama > /dev/null 2>&1; then \
			echo "     Pulling chat model: $$CHAT_MODEL"; \
			ollama pull $$CHAT_MODEL || true; \
		else \
			echo "     Ollama not found. Install for local chat: brew install ollama && ollama serve"; \
		fi; \
	elif [ "$$PROVIDER" = "google" ]; then \
		echo "     Using Gemini for chat + embeddings (cloud mode)."; \
		echo "     Ollama models will NOT be pulled (not needed)."; \
		if command -v ollama > /dev/null 2>&1; then \
			echo "     (Ollama is available as fallback if needed)"; \
		fi; \
	elif command -v ollama > /dev/null 2>&1; then \
		EMBED_MODEL=$$(grep -E '^OLLAMA_EMBED_MODEL=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
		EMBED_MODEL=$${EMBED_MODEL:-nomic-embed-text}; \
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
	@echo "Seeding Firestore (skipped if data exists)..."
	@$(MAKE) seed-firestore-if-empty
	@echo ""
	@echo "Starting backend (logs → .logs/backend.log)..."
	@cd CHATVOTE-BackEnd && \
		poetry run watchfiles --filter python \
		"python -m src.aiohttp_app --debug" src/ \
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
	@for i in $$(seq 1 45); do \
		if curl -sf -m 2 http://localhost:3000/ > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@echo ""
	@echo "=== All services running ==="
	@echo ""
	@$(MAKE) check
	@echo ""
	@echo "  App:                http://localhost:3000"
	@echo "  Qdrant dashboard:   http://localhost:6333/dashboard"
	@echo "  Firebase emulators: http://localhost:4000"
	@echo "  Langfuse dashboard: http://localhost:8652"
	@echo ""
	@echo "  Logs:  make logs           (tail all logs)"
	@echo "  Stop:  make stop           (stop everything)"
	@echo ""

dev-infra:
	@PROFILES=""; \
	EMBED_PROV=$$(grep -E '^EMBEDDING_PROVIDER=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	HAS_GOOGLE_KEY=$$(grep -E '^GOOGLE_API_KEY=.+' CHATVOTE-BackEnd/.env 2>/dev/null | head -1); \
	NEEDS_OLLAMA=true; \
	if [ "$$EMBED_PROV" = "google" ] && [ -n "$$HAS_GOOGLE_KEY" ]; then \
		echo "Using Gemini for chat + embeddings (cloud mode) — Ollama not needed."; \
		NEEDS_OLLAMA=false; \
	elif [ "$$EMBED_PROV" = "scaleway" ] && [ -n "$$HAS_GOOGLE_KEY" ]; then \
		echo "Using Scaleway embeddings + Gemini chat (cloud mode) — Ollama not needed."; \
		NEEDS_OLLAMA=false; \
	fi; \
	if [ "$$NEEDS_OLLAMA" = "true" ]; then \
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
	fi; \
	if curl -sf http://localhost:8081/ > /dev/null 2>&1 && curl -sf http://localhost:9099/ > /dev/null 2>&1; then \
		echo "Native Firebase emulators detected on :8081/:9099 — skipping Docker emulators."; \
	else \
		echo "Starting Firebase emulators in Docker (Firestore :8081, Auth :9099)..."; \
		PROFILES="$$PROFILES --profile firebase"; \
	fi; \
	echo "Starting Langfuse observability (dashboard :3001)..."; \
	PROFILES="$$PROFILES --profile langfuse"; \
	if [ "$$RAGFLOW" = "1" ]; then \
		echo "Starting RAGFlow (web UI :8680, API :9380)..."; \
		PROFILES="$$PROFILES --profile ragflow"; \
	fi; \
	docker compose -f docker-compose.dev.yml $$PROFILES up -d --wait

# Backward-compat alias — Firebase emulators now run inside Docker via dev-infra
dev-emulators: dev-infra

# ---------------------------------------------------------------------------
# Run a single service in the foreground (for debugging)
# ---------------------------------------------------------------------------

dev-backend:
	cd CHATVOTE-BackEnd && poetry run watchfiles --filter python "python -m src.aiohttp_app --debug" src/

dev-frontend:
	cd CHATVOTE-FrontEnd && npm run dev

# ---------------------------------------------------------------------------
# Data seeding
# ---------------------------------------------------------------------------

seed:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py --with-vectors

seed-local:
	cd CHATVOTE-BackEnd && EMBEDDING_PROVIDER=ollama poetry run python scripts/seed_local.py --with-vectors

seed-qwen:
	@if [ -z "$$(grep -E '^SCALEWAY_EMBED_API_KEY=' CHATVOTE-BackEnd/.env 2>/dev/null | cut -d= -f2)" ]; then \
		echo "Error: SCALEWAY_EMBED_API_KEY not set in CHATVOTE-BackEnd/.env"; \
		echo "Add your Scaleway API key to CHATVOTE-BackEnd/.env"; \
		exit 1; \
	fi
	cd CHATVOTE-BackEnd && EMBEDDING_PROVIDER=scaleway poetry run python scripts/seed_local.py --with-vectors

seed-snapshots:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py --restore-snapshots

seed-firestore:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py

seed-firestore-if-empty:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py --skip-if-exists

snapshot:
	@echo "=== Exporting current dev data as seed ==="
	@echo "Exporting Firebase emulator data..."
	@docker exec chatvote-firebase-emulators-1 npx firebase emulators:export /firebase/emulator-data --project chat-vote-dev --force
	@echo "Exporting Qdrant snapshots..."
	@mkdir -p CHATVOTE-BackEnd/qdrant_snapshots
	@cd CHATVOTE-BackEnd && poetry run python -c "\
	from qdrant_client import QdrantClient; \
	import json, os; \
	client = QdrantClient(url='http://localhost:6333'); \
	provider = os.getenv('EMBEDDING_PROVIDER', 'unknown'); \
	for col in client.get_collections().collections: \
	    info = client.get_collection(col.name); \
	    print(f'Snapshotting {col.name} ({info.points_count} points)...'); \
	    snap = client.create_snapshot(col.name); \
	    print(f'  → {snap.name}'); \
	meta = { \
	    'embedding_provider': provider, \
	    'collections': [c.name for c in client.get_collections().collections], \
	}; \
	open('qdrant_snapshots/snapshot_meta.json','w').write(json.dumps(meta, indent=2)); \
	print(f'Metadata saved (provider={provider})');"
	@echo ""
	@echo "=== Snapshot complete ==="
	@echo "  Firebase: CHATVOTE-BackEnd/firebase/emulator-data/"
	@echo "  Qdrant:   snapshots stored in Qdrant (use API to download)"
	@echo "  Metadata: CHATVOTE-BackEnd/qdrant_snapshots/snapshot_meta.json"

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
	@EMBED_PROV=$$(grep -E '^EMBEDDING_PROVIDER=' CHATVOTE-BackEnd/.env 2>/dev/null | tail -1 | cut -d= -f2); \
	HAS_GOOGLE_KEY=$$(grep -E '^GOOGLE_API_KEY=.+' CHATVOTE-BackEnd/.env 2>/dev/null | head -1); \
	if [ "$$EMBED_PROV" != "google" ] || [ -z "$$HAS_GOOGLE_KEY" ]; then \
		if [ "$$EMBED_PROV" != "scaleway" ] || [ -z "$$HAS_GOOGLE_KEY" ]; then \
			printf "  Ollama    (:11434) ... " && \
			(curl -sf http://localhost:11434/ > /dev/null 2>&1 && echo "OK" || echo "FAIL"); \
		fi; \
	fi
	@printf "  Firestore (:8081)  ... " && \
		(curl -sf http://localhost:8081/ > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Auth      (:9099)  ... " && \
		(curl -sf http://localhost:9099/ > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Backend   (:8080)  ... " && \
		(curl -sf http://localhost:8080/healthz > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Frontend  (:3000)  ... " && \
		(curl -sf -m 5 http://localhost:3000/ > /dev/null 2>&1 && echo "OK" || echo "FAIL")
	@printf "  Langfuse  (:3001)  ... " && \
		(curl -sf http://localhost:8652/api/public/health > /dev/null 2>&1 && echo "OK" || echo "FAIL")

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

logs:
	@tail -f .logs/backend.log .logs/frontend.log

# ---------------------------------------------------------------------------
# Production logs — unified view across all services
# ---------------------------------------------------------------------------

SINCE ?= 5m
LINES ?= 30

logs-prod:
	@bash scripts/logs-prod.sh all

logs-backend:
	@bash scripts/logs-prod.sh backend

logs-frontend:
	@bash scripts/logs-prod.sh frontend

logs-qdrant:
	@bash scripts/logs-prod.sh qdrant

logs-k8s:
	@bash scripts/logs-prod.sh k8s

check-prod:
	@bash scripts/logs-prod.sh health

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

stop:
	@echo "Stopping all services..."
	docker compose -f docker-compose.dev.yml --profile ollama --profile firebase --profile langfuse --profile ragflow down
	@for svc in backend frontend; do \
		if [ -f .logs/$$svc.pid ]; then \
			kill $$(cat .logs/$$svc.pid) 2>/dev/null || true; \
			rm -f .logs/$$svc.pid; \
			echo "  $$svc stopped."; \
		fi; \
	done
	@lsof -ti :8080 2>/dev/null | xargs kill -9 2>/dev/null && echo "  backend orphans killed." || true
	@lsof -ti :3000 2>/dev/null | xargs kill -9 2>/dev/null && echo "  frontend orphans killed." || true
	@pkill -9 -f "detached-flush.js.*CHATVOTE-FrontEnd" 2>/dev/null && echo "  next.js telemetry zombies killed." || true
	@rm -f CHATVOTE-FrontEnd/.next/dev/lock
	@lsof -ti :9099,:8081,:9199 2>/dev/null | sort -u | xargs kill 2>/dev/null && echo "  native firebase emulators stopped." || true
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
	docker compose -f docker-compose.dev.yml --profile ollama --profile firebase --profile langfuse --profile ragflow down -v
