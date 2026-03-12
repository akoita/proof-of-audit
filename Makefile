.PHONY: test-contracts test-python

test-contracts:
	forge test --root contracts

test-python:
	PYTHONPATH=agent:api python3 -m unittest discover -s agent/tests
	PYTHONPATH=agent:api python3 -m unittest discover -s api/tests

