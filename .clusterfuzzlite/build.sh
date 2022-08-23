# Build and install project (using current CFLAGS, CXXFLAGS).
pip3 install .

# Build fuzzers in $OUT.
for fuzzer in $(find $SRC -name 'fuzz_*.py'); do
  compile_python_fuzzer $fuzzer
done
