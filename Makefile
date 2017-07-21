export PYTHONASYNCIODEBUG=1
export PYTHONWARNINGS=default
export CFLAGS=-O0 -coverage
export LDFLAGS=-coverage

test:
	python -m unittest

coverage:
	python setup.py build_ext --inplace
	python -m coverage erase
	python -m coverage run --branch --source=websockets -m unittest
	python -m coverage html
	gcovr -r . --html --html-details -o htmlcov/speedups.html

clean:
	python setup.py cleanext clean --all
	find . -name '*.pyc' -delete
	find . -name __pycache__ -delete
	rm -rf .coverage build compliance/reports dist docs/_build htmlcov MANIFEST README websockets.egg-info
