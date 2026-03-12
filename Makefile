.PHONY: anvil deploy-local install-api-deps test-contracts test-python

PYTHON ?= python3

anvil:
	./scripts/start-anvil.sh

deploy-local:
	./scripts/deploy-local.sh

install-api-deps:
	$(PYTHON) -m pip install -r api/requirements.txt

test-contracts:
	forge test --root contracts

test-python:
	PYTHONPATH=agent:api $(PYTHON) -m unittest discover -s agent/tests
	PYTHONPATH=agent:api $(PYTHON) -m unittest discover -s api/tests
