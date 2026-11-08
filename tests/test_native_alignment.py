import pathlib
import struct
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts/build'))
from wrap_native_image import wrap, TEXT_OFFSET, PADDING, ALIGNMENT


def kernel():
    image = bytearray(4096)
    struct.pack_into('<3Q', image, 8, 0, 8192, 0xa)
    image[56:60] = b'ARM\x64'
    image[64:] = b'K'*(4096-64)
    return bytes(image)


class NativeAlignmentTest(unittest.TestCase):
    def test_branch_targets_unmodified_original_and_preserves_runtime_extent(self):
        original = kernel()
        result = wrap(original)
        branch, nop = struct.unpack_from('<II', result)
        self.assertEqual(branch >> 26, 0b000101)  # A64 unconditional B, no link
        target = (branch & 0x3ffffff)*4
        self.assertEqual(target, PADDING)
        self.assertEqual(result[target:], original)
        self.assertEqual(nop, 0xd503201f)
        self.assertEqual(struct.unpack_from('<Q', result, 8)[0], TEXT_OFFSET)
        self.assertEqual(struct.unpack_from('<Q', result, 16)[0], PADDING+8192)
        self.assertEqual(result[60:64], bytes(4))  # no EFI PE header offset
        for base in (0, 0xa0000000, 0x180000000):
            entry = base+TEXT_OFFSET+target
            self.assertEqual(entry % ALIGNMENT, 0)
            self.assertEqual(entry+8192, base+TEXT_OFFSET+PADDING+8192)

    def test_nonzero_original_offset_rejected(self):
        data = bytearray(kernel())
        struct.pack_into('<Q', data, 8, 0x80000)
        with self.assertRaises(ValueError):
            wrap(data)

    def test_truncated_or_invalid_image_rejected(self):
        with self.assertRaises(ValueError):
            wrap(b'not an image')
        data = bytearray(kernel())
        struct.pack_into('<Q', data, 16, 1)
        with self.assertRaises(ValueError):
            wrap(data)

    def test_non_4k_image_rejected(self):
        data = bytearray(kernel())
        struct.pack_into('<Q', data, 24, 0xc)
        with self.assertRaises(ValueError):
            wrap(data)
