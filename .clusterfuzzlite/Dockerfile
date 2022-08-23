FROM gcr.io/oss-fuzz-base/base-builder-python
RUN git clone --branch clusterfuzzlite --depth 1 https://github.com/aaugustin/websockets
WORKDIR websockets
COPY .clusterfuzzlite/build.sh $SRC/
