export PYTHONASYNCIODEBUG=1
export PYTHONWARNINGS=default

test:
	python -m unittest

coverage:
	python -m coverage erase
	python -m coverage run --branch --source=websockets -m unittest
	python -m coverage html

clean:
	find . -name '*.pyc' -delete
	find . -name __pycache__ -delete
	rm -rf .coverage build compliance/reports dist docs/_build htmlcov MANIFEST README websockets.egg-info
