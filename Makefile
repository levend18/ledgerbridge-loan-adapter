.PHONY: up down lint test verify seed bench build hooks migrate
up:
	docker compose up -d --wait
down:
	docker compose down
build:
	docker compose build dev frontend
lint:
	docker compose run --rm dev sh -c 'ruff check . && ruff format --check . && mypy && lint-imports'
	docker compose run --rm dev sh -c 'cargo fmt --manifest-path adapter/quality/engine/Cargo.toml --check && cargo clippy --locked --manifest-path adapter/quality/engine/Cargo.toml -- -D warnings'
	docker compose run --rm --no-deps frontend npm run lint
test: migrate
	docker compose stop beat worker
	docker compose run --rm dev cargo test --locked --manifest-path adapter/quality/engine/Cargo.toml
	docker compose run --rm dev pytest tests/unit tests/integration -q -m "not live_worker"
	docker compose run --rm --no-deps frontend sh -c 'npm run build && npm test'
migrate:
	docker compose run --rm dev sh -c 'python -m tools.bootstrap_db && python manage.py migrate --noinput'
hooks:
	git config core.hooksPath .githooks
verify:
	docker compose stop beat worker
	docker compose run --rm dev pytest tests/verification -q -m "not live_worker"
seed: migrate
	docker compose stop beat worker
	docker compose run --rm dev python -m tools.seed
	docker compose up -d worker beat
bench:
	docker compose run --rm dev python tools/bench.py

test-live:
	docker compose up -d worker
	POLL_INTERVAL_SECONDS=5 docker compose up -d beat
	docker compose run --rm dev pytest tests/integration/test_poll.py -q
	docker compose stop beat worker
