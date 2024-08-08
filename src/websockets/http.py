from __future__ import annotations

import typing

from .imports import lazy_import


# For backwards compatibility:


# When type checking, import non-deprecated aliases eagerly. Else, import on demand.
if typing.TYPE_CHECKING:
    from .datastructures import Headers, MultipleValuesError  # noqa: F401
else:
    lazy_import(
        globals(),
        # Headers and MultipleValuesError used to be defined in this module.
        aliases={
            "Headers": ".datastructures",
            "MultipleValuesError": ".datastructures",
        },
        deprecated_aliases={
            "read_request": ".legacy.http",
            "read_response": ".legacy.http",
        },
    )
