.PHONY: anvil deploy-local deploy-demo-fixtures install-api-deps test-contracts test-python test-e2e

PYTHON ?= python3

anvil:
	./scripts/start-anvil.sh

deploy-local:
	./scripts/deploy-local.sh

deploy-demo-fixtures:
	./scripts/deploy-demo-fixtures.sh

install-api-deps:
	$(PYTHON) -m pip install setuptools wheel
	$(PYTHON) -m pip install --no-build-isolation -e '.[dev]'

test-contracts:
	forge test --root contracts

test-python:
	PYTHONPATH=agent:api $(PYTHON) -m pytest

test-e2e:
	cd web && PYTHON_BIN=$${PYTHON_BIN:-$(PYTHON)} pnpm exec playwright test
