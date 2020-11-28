import warnings


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", "websockets.framing is deprecated", DeprecationWarning
    )
    # Check that the legacy framing module imports without an exception.
    from websockets.framing import *  # noqa
