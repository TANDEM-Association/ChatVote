.PHONY: dev-infra seed seed-vectors dev-backend dev-frontend dev stop clean

dev-infra:
	docker compose -f docker-compose.dev.yml up -d

seed:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py

seed-vectors:
	cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py --with-vectors

dev-backend:
	cd CHATVOTE-BackEnd && poetry run python -m src.aiohttp_app --debug

dev-frontend:
	cd CHATVOTE-FrontEnd && npm run dev

dev: dev-infra
	@echo ""
	@echo "=== Infrastructure is up ==="
	@echo "  Qdrant:  http://localhost:6333/dashboard"
	@echo "  Ollama:  http://localhost:11434"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Start Firebase emulators:  cd CHATVOTE-BackEnd/firebase && npx firebase emulators:start --project chat-vote-dev --only firestore,auth"
	@echo "  2. Seed data:                 make seed"
	@echo "  3. Start backend:             make dev-backend"
	@echo "  4. Start frontend:            make dev-frontend"
	@echo ""

stop:
	docker compose -f docker-compose.dev.yml down

clean:
	docker compose -f docker-compose.dev.yml down -v
