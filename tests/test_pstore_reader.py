import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/build'))
from prepare_pstore_reader import patch_tree


def tree(value=0x1000):
    def begin(name):
        data = name.encode() + b'\0'
        return struct.pack('>I', 1) + data + bytes(-len(data) % 4)
    data = begin('') + begin('reserved-memory') + begin('ramoops@0xB0000000')
    data += struct.pack('>IIII', 3, 4, 0, value)
    data += struct.pack('>IIII', 2, 2, 2, 9)
    strings = b'devinfo-size\0'
    total = 40 + len(data) + len(strings)
    return struct.pack('>10I', 0xd00dfeed, total, 40, 40 + len(data), 0,
                       17, 16, 0, len(strings), len(data)) + data + strings


class PstoreReaderPatchTest(unittest.TestCase):
    def test_concatenated_tree_at_unaligned_file_offset(self):
        # Stock DTBs are concatenated without aligning each following blob.
        original = b'abc' + tree()
        image = bytearray(original)
        size, changed = patch_tree(image, 3)
        self.assertEqual(size, len(original) - 3)
        self.assertEqual(len(changed), 1)
        self.assertEqual(struct.unpack_from('>I', image, changed[0])[0], 0)
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, image)) if a != b],
                         [changed[0] + 2])

    def test_unexpected_original_size_is_rejected(self):
        with self.assertRaises(ValueError):
            patch_tree(bytearray(tree(0x2000)), 0)


if __name__ == '__main__':
    unittest.main()
