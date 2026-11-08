import pathlib
import struct
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts/build'))
from prepare_stock_table_noop import replace_entry


def fixture():
    image = bytearray(512)
    struct.pack_into('>8I', image, 0, 0xd7b7ab1e, 400, 32, 32, 2, 32, 4096, 0)
    struct.pack_into('>2I', image, 32, 80, 128)
    struct.pack_into('>2I', image, 64, 80, 256)
    image[128:208] = b'A'*80
    image[256:336] = b'B'*80
    image[400:] = b'Z'*112
    return bytes(image)


class DtboSlotTest(unittest.TestCase):
    def test_selected_slot_only_and_trailing_metadata_preserved(self):
        original = fixture()
        replacement = struct.pack('>II', 0xd00dfeed, 16)+b'C'*8
        result, slot = replace_entry(original, 1, replacement)
        self.assertEqual(slot, (256, 336))
        self.assertEqual(result[:64], original[:64])
        self.assertEqual(result[68:256], original[68:256])
        self.assertEqual(result[336:], original[336:])
        self.assertEqual(result[256:272], replacement)
        self.assertEqual(result[272:336], bytes(64))
        self.assertEqual(struct.unpack_from('>I', result, 64)[0], 16)

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            replace_entry(fixture(), 1, bytes(81))

    def test_overlapping_slots_rejected(self):
        image = bytearray(fixture())
        struct.pack_into('>I', image, 68, 160)
        with self.assertRaises(ValueError):
            replace_entry(image, 1, b'')

    def test_truncated_table_rejected(self):
        with self.assertRaises(ValueError):
            replace_entry(fixture()[:120], 1, b'')
