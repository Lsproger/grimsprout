.PHONY: fmt lint test check

fmt:
	ruff format src/ tests/

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

test:
	pytest 

check: lint test