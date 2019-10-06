import logging
import warnings


# Avoid displaying stack traces at the ERROR logging level.
logging.basicConfig(level=logging.CRITICAL)


# Ignore deprecation warnings while refactoring is in progress
warnings.filterwarnings(
    action="ignore",
    message=r"websockets\.framing is deprecated",
    category=DeprecationWarning,
    module="websockets.framing",
)
