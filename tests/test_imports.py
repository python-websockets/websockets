import types
import unittest
import warnings

from websockets.imports import *


foo = object()

bar = object()


class ImportsTests(unittest.TestCase):
    def test_get_alias(self):
        mod = types.ModuleType("tests.test_imports.test_alias")
        lazy_import(vars(mod), aliases={"foo": ".."})

        self.assertEqual(mod.foo, foo)

    def test_get_deprecated_alias(self):
        mod = types.ModuleType("tests.test_imports.test_alias")
        lazy_import(vars(mod), deprecated_aliases={"bar": ".."})

        with warnings.catch_warnings(record=True) as recorded_warnings:
            self.assertEqual(mod.bar, bar)

        self.assertEqual(len(recorded_warnings), 1)
        warning = recorded_warnings[0].message
        self.assertEqual(
            str(warning), "tests.test_imports.test_alias.bar is deprecated"
        )
        self.assertEqual(type(warning), DeprecationWarning)

    def test_dir(self):
        mod = types.ModuleType("tests.test_imports.test_alias")
        lazy_import(vars(mod), aliases={"foo": ".."}, deprecated_aliases={"bar": ".."})

        self.assertEqual(
            [item for item in dir(mod) if not item[:2] == item[-2:] == "__"],
            ["bar", "foo"],
        )

    def test_attribute_error(self):
        mod = types.ModuleType("tests.test_imports.test_alias")
        lazy_import(vars(mod))

        with self.assertRaises(AttributeError) as raised:
            mod.foo

        self.assertEqual(
            str(raised.exception),
            "module 'tests.test_imports.test_alias' has no attribute 'foo'",
        )
