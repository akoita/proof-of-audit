.PHONY: anvil deploy-local deploy-demo-fixtures deploy-base-sepolia deploy-base-sepolia-identity verify-base-sepolia install-api-deps install-git-hooks security-audit-staged test-contracts test-python test-system-e2e test-testnet-smoke test-ui-e2e test-e2e

PYTHON ?= python3

anvil:
	./scripts/start-anvil.sh

deploy-local:
	./scripts/deploy-local.sh

deploy-demo-fixtures:
	./scripts/deploy-demo-fixtures.sh

deploy-base-sepolia:
	./scripts/deploy-base-sepolia.sh

deploy-base-sepolia-identity:
	./scripts/deploy-base-sepolia-identity.sh

verify-base-sepolia:
	./scripts/verify-base-sepolia.sh

install-api-deps:
	$(PYTHON) -m pip install setuptools wheel
	$(PYTHON) -m pip install --no-build-isolation -e '.[dev]'

install-git-hooks:
	./scripts/install-git-hooks.sh

security-audit-staged:
	PYTHON_BIN=$${PYTHON_BIN:-$(PYTHON)} ./scripts/run-pre-commit-security-audit.sh

test-contracts:
	forge test --root contracts

test-python:
	PYTHONPATH=agent:api $(PYTHON) -m pytest -m "not system_e2e"

test-system-e2e:
	PYTHONPATH=agent:api $(PYTHON) -m pytest -m system_e2e api/tests

test-testnet-smoke:
	PYTHONPATH=agent:api $(PYTHON) -m pytest -m testnet_smoke api/tests/testnet

test-ui-e2e:
	cd web && CI=1 PYTHON_BIN=$${PYTHON_BIN:-$(PYTHON)} pnpm exec playwright test

test-e2e: test-system-e2e test-ui-e2e
