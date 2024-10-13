.PHONY: default style types tests coverage maxi_cov build clean

export PYTHONASYNCIODEBUG=1
export PYTHONPATH=src
export PYTHONWARNINGS=default

build:
	python setup.py build_ext --inplace

style:
	ruff format compliance src tests
	ruff check --fix compliance src tests

types:
	mypy --strict src

tests:
	python -m unittest

coverage:
	coverage run --source src/websockets,tests -m unittest
	coverage html
	coverage report --show-missing --fail-under=100

maxi_cov:
	python tests/maxi_cov.py
	coverage html
	coverage report --show-missing --fail-under=100

clean:
	find src -name '*.so' -delete
	find . -name '*.pyc' -delete
	find . -name __pycache__ -delete
	rm -rf .coverage .mypy_cache build compliance/reports dist docs/_build htmlcov MANIFEST src/websockets.egg-info
