import importlib
import sys
import warnings
from typing import Any, Dict, Iterable, Optional


__all__ = ["lazy_import"]


def lazy_import(
    namespace: Dict[str, Any],
    aliases: Optional[Dict[str, str]] = None,
    deprecated_aliases: Optional[Dict[str, str]] = None,
) -> None:
    """
    Provide lazy, module-level imports.

    Typical use::

        __getattr__, __dir__ = lazy_import(
            globals(),
            aliases={
                "<name>": "<source module>",
                ...
            },
            deprecated_aliases={
                ...,
            }
        )

    This function defines __getattr__ and __dir__ per PEP 562.

    On Python 3.6 and earlier, it falls back to non-lazy imports and doesn't
    raise deprecation warnings.

    """
    if aliases is None:
        aliases = {}
    if deprecated_aliases is None:
        deprecated_aliases = {}

    namespace_set = set(namespace)
    aliases_set = set(aliases)
    deprecated_aliases_set = set(deprecated_aliases)

    assert not namespace_set & aliases_set, "namespace conflict"
    assert not namespace_set & deprecated_aliases_set, "namespace conflict"
    assert not aliases_set & deprecated_aliases_set, "namespace conflict"

    package = namespace["__name__"]

    if sys.version_info[:2] >= (3, 7):

        def __getattr__(name: str) -> Any:
            assert aliases is not None  # mypy cannot figure this out
            try:
                source = aliases[name]
            except KeyError:
                pass
            else:
                module = importlib.import_module(source, package)
                return getattr(module, name)

            assert deprecated_aliases is not None  # mypy cannot figure this out
            try:
                source = deprecated_aliases[name]
            except KeyError:
                pass
            else:
                warnings.warn(
                    f"{package}.{name} is deprecated",
                    DeprecationWarning,
                    stacklevel=2,
                )
                module = importlib.import_module(source, package)
                return getattr(module, name)

            raise AttributeError(f"module {package!r} has no attribute {name!r}")

        namespace["__getattr__"] = __getattr__

        def __dir__() -> Iterable[str]:
            return sorted(namespace_set | aliases_set | deprecated_aliases_set)

        namespace["__dir__"] = __dir__

    else:  # pragma: no cover

        for name, source in aliases.items():
            module = importlib.import_module(source, package)
            namespace[name] = getattr(module, name)

        for name, source in deprecated_aliases.items():
            module = importlib.import_module(source, package)
            namespace[name] = getattr(module, name)
