install_uv:
	@if [ -f "uv" ]; then echo "Downloading uv" && curl -LsSf https://astral.sh/uv/install.sh | sh; else echo "uv already installed"; fi
	uv self update

install_python:
	uv python install

install_deps:
	uv sync --all-extras

install_precommit:
	uv run pre-commit install
	uv run pre-commit gc

update_precommit:
	uv run pre-commit autoupdate
	uv run pre-commit gc

precommit:
	uv run pre-commit run --all-files

test:
	uv run pytest tests

compose:
	chmod a+rw configs/grafana/dashboards
	docker compose up --build
tests: test
install: install_uv install_python install_deps install_precommit


docker_receiver:
	docker buildx build -t receiver -f Dockerfile --build-arg PACKAGE=receiver .
	docker run -p 8000:8000 -e PORT=8000 -it receiver

docker_poller:
	docker buildx build -t poller -f Dockerfile --build-arg PACKAGE=poller .
	docker run -p 8000:8000 -e PORT=8000 -it poller
