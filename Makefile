# ProofPatch — top-level developer entry points.
#
#   make setup     create the venv, install Python + JS dependencies
#   make test      run the engine test suite
#   make demo      reset and run the end-to-end fixture demo
#   make api       start the FastAPI server (dashboard served if built)
#   make web       start the Vite dev server

PYTHON  := .venv/bin/python
PIP     := .venv/bin/pip
RUFF    := .venv/bin/ruff
PROOFPATCH := .venv/bin/proofpatch

.PHONY: setup install install-py install-web install-bridge test lint build web api demo reset clean

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(MAKE) install
	bash scripts/setup_fixture.sh

install: install-py install-web install-bridge

install-py:
	$(PIP) install -e "./packages/engine[dev]" -e ./apps/api

install-web:
	cd apps/web && npm install

# Cline SDK agent bridge (Node 22+)
install-bridge:
	cd packages/cline-bridge && npm install

test:
	$(PYTHON) -m pytest packages/engine apps/api

lint:
	$(RUFF) check --config ruff.toml packages/engine apps/api fixtures/python-session-bug/src fixtures/python-session-bug/tests

build-web:
	cd apps/web && npm run build

api:
	$(PYTHON) -m uvicorn proofpatch_api.main:app --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev

demo:
	bash scripts/demo.sh

reset:
	bash scripts/reset_demo.sh

clean:
	rm -rf .proofpatch .pytest_cache packages/engine/.pytest_cache
	find . -name '__pycache__' -type d -prune -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
