.PHONY: anvil deploy-local deploy-demo-fixtures install-api-deps test-contracts test-python test-e2e

PYTHON ?= python3

anvil:
	./scripts/start-anvil.sh

deploy-local:
	./scripts/deploy-local.sh

deploy-demo-fixtures:
	./scripts/deploy-demo-fixtures.sh

install-api-deps:
	$(PYTHON) -m pip install -r api/requirements.txt

test-contracts:
	forge test --root contracts

test-python:
	PYTHONPATH=agent:api $(PYTHON) -m unittest discover -s agent/tests
	PYTHONPATH=agent:api $(PYTHON) -m unittest discover -s api/tests

test-e2e:
	cd web && PYTHON_BIN=$(PYTHON) pnpm exec playwright test
