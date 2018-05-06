export PYTHONASYNCIODEBUG=1
export PYTHONWARNINGS=default

test:
	python -m unittest

coverage:
	python -m coverage erase
	python -m coverage run --branch --source=websockets -m unittest
	python -m coverage html

nosse2.gcov: CFLAGS=-mno-sse2
%.gcov: websockets/speedups.c
	find . \( -name '*.so' -o -name '*.gcno' -o -name '*.gcda' \) -delete
	CFLAGS="-O0 -coverage $(CFLAGS)" LDFLAGS="-coverage" python setup.py --quiet build_ext --inplace
	python -m unittest
	find . -name '*.gcda' -exec gcov -abcflp -o {} websockets/speedups.c \; > /dev/null
	find . -name 'websockets#speedups.c.gcov' -exec mv {} $@ \;

ccoverage: default.gcov nosse2.gcov
	mkdir -p htmlcov
	gcovr -g -r . -s -k --html --html-details -o htmlcov/speedups.html #'-k': keep gcov data

clean:
	find . \( -name '*.pyc' -o -name '*.so' -o -name '*.gcno' -o -name '*.gcda' -o -name '*.gcov' \) -delete
	find . -name __pycache__ -delete
	rm -rf .coverage build compliance/reports dist docs/_build htmlcov MANIFEST README websockets.egg-info
