import unittest

from .utils import apply_mask as py_apply_mask


class UtilsTests(unittest.TestCase):

    @staticmethod
    def apply_mask(*args, **kwargs):
        return py_apply_mask(*args, **kwargs)

    def test_apply_mask(self):
        input = b'abcdABCD' * 8
        output = b'PPPPpppp' * 8
        for i in range(0, 64):
            self.assertEqual(self.apply_mask(input[0:i], b'1234'), output[0:i])

    def test_apply_mask_check_input_types(self):
        for data_in, mask in [
            (None, None),
            (b'abcd', None),
            (None, b'abcd'),
        ]:
            with self.assertRaises(TypeError):
                self.apply_mask(data_in, mask)

    def test_apply_mask_check_mask_length(self):
        for data_in, mask in [
            (b'', b''),
            (b'abcd', b'123'),
            (b'', b'aBcDe'),
            (b'12345678', b'12345678'),
        ]:
            with self.assertRaises(ValueError):
                self.apply_mask(data_in, mask)


try:
    from .speedups import apply_mask as c_apply_mask
except ImportError:
    pass
else:
    class SpeedupsTests(UtilsTests):

        @staticmethod
        def apply_mask(*args, **kwargs):
            return c_apply_mask(*args, **kwargs)
