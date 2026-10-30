# Guidance for coding agents

## Project overview

websockets is a Python implementation of the WebSocket protocol (RFC 6455).

Its priorities are correctness, simplicity, robustness, and performance.

## Architecture & layout

websockets provides five implementations:

* a [Sans-I/O](https://sans-io.readthedocs.io/) protocol implementation
  in `src/websockets/`
* three I/O integrations
  * asyncio in `src/websockets/asyncio/`
  * threading in `src/websockets/sync/`
  * trio in `src/websockets/trio/`
* legacy implementation in `src/websockets/legacy/`

The Sans-I/O protocol implementation contains notably:

* `protocol.py` and `frames.py`: core protocol
* `extensions/permessage_deflate.py`: compression (RFC 7692)
* `client.py` and `server.py`: opening handshake

Each I/O integration includes:

* `connection.py`: `Connection` provides I/O integration
* `messages.py`: `Assembler` reassembles fragmented messages
* `client.py`: `connect` is the entrypoint for clients
* `server.py`: `serve` is the entrypoint for servers; also defines `Server`
* `router.py`: `route` adds URL routing with `werkzeug`

A CLI is defined in `src/websockets/cli.py`.

Lazy imports with `src/websockets/imports.py` make it possible to import from
the `websockets` root package while loading only modules that are really used.

## Environment

A Python environment with all required dependencies is configured with direnv,
and the local repository is installed there.

Prefix all commands with `direnv exec . ` to run them in this environment.

## Tests

Every source module has a matching test module e.g.
`src/websockets/protocol.py -> tests/test_protocol.py`.

Run tests for a module with `python -m unittest ...` e.g.
`direnv exec . python -m unittest tests.test_protocol`.

Run a single test with `python -m unittest -k ...` e.g.
`direnv exec . python -m unittest -k test_client_sends_text`.

Run the entire test suite with `direnv exec . make tests`. It takes ~15 seconds.

Each source module must have a test module providing 100% branch coverage,
except for the legacy implementation and four modules without testable logic.

Check this requirement with `direnv exec . make maxi_cov`. It takes ~30 seconds.

When encountering a flaky test, re-run with WEBSOCKETS_TESTS_TIMEOUT_FACTOR=10.

## Docs

Documentation follows the [Diataxis](https://diataxis.fr/) framework.

* tutorials in `docs/intro`
* how-to guides in `docs/howto`, `docs/deploy`, and `docs/faq`
* explanations in `docs/topics`
* API reference in `docs/reference`, generated from docstrings

## Making changes

* Avoid backwards-incompatible changes to documented APIs.

* Keep changes minimal. Write terse comments. Ask before adding tests.

* When changing an I/O integration, review the other I/O integrations and
  determine if the same change must be applied. Code, tests, and docs are
  highly consistent across integrations; they must remain in sync.

* When a change has user-visible consequences, include a short changelog entry
  in `docs/project/changelog.rst`.

* When finalizing a change, always format code with `direnv exec . make style`,
  check types with `direnv exec . make types`, and ensure test coverage with
  `direnv exec . make maxi_cov`.

* Don't edit the legacy implementation, unless requested specifically. If you
  do, ensure test coverage with `direnv exec . make coverage`.

* Write code compatible with Python 3.11+.

## Code style

* Never prefix variable and class names with an underscore. This project doesn't
  use the _-prefix convention for private APIs.

## Development commands

Run commands from the repository root, prefixed with `direnv exec . `.

```bash
make build       # Build the C extension - only needed after changing speedups.c
make tests       # Run the test suite
make coverage    # Run tests and require 100% branch coverage
make maxi_cov    # Run tests, except legacy, and require 100% per-module branch coverage
make types       # Run mypy in strict mode
make style       # Format and auto-fix code with ruff
make spell       # Apply codespell fixes - not needed
make clean       # Remove build artifacts and generated files - not needed
```
