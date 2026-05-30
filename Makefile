.PHONY: dev test build

dev:
	cd infra && docker-compose up --build -d
	@echo "TrustShield dev stack is running!"
	@echo "Seeding DB with sample data..."
	# docker exec trustshield-api-1 python scripts/seed_db.py

stop:
	cd infra && docker-compose down

test:
	cd backend && PYTHONPATH=$(PWD)/backend pytest tests/integration/

build-frontend:
	cd frontend && npm run build