import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts/build'))
from avb_footer import parse_footer, retain_envelope


class AvbEnvelopeTest(unittest.TestCase):
    def stock(self):
        image = bytearray(16384)
        metadata = bytearray(448)
        metadata[:4] = b'AVB0'
        struct.pack_into('>QQ', metadata, 12, 64, 128)
        image[4096:4544] = metadata
        struct.pack_into('>4sIIQQQ28s', image, len(image)-64, b'AVBf', 1, 0, 100, 4096, 448, b'\0'*28)
        return bytes(image)

    def test_payload_and_metadata_are_kept_with_updated_footer_location(self):
        stock = self.stock()
        payload = b'x'*6145
        image, report = retain_envelope(stock, payload)
        self.assertEqual(len(image), 16384)
        self.assertEqual(image[:6145], payload)
        self.assertEqual(image[8192:8640], stock[4096:4544])
        self.assertEqual(struct.unpack_from('>QQQ', image, len(image)-52), (6145, 8192, 448))
        self.assertEqual(parse_footer(image)['original_size'], 6145)

    def test_missing_footer_is_rejected(self):
        with self.assertRaises(ValueError):
            retain_envelope(bytes(16384), b'payload')

    def test_oversize_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            retain_envelope(self.stock(), bytes(16300))

    def test_invalid_embedded_metadata_is_rejected(self):
        image = bytearray(self.stock())
        image[4096:4100] = b'xxxx'
        with self.assertRaises(ValueError):
            parse_footer(image)


if __name__ == '__main__':
    unittest.main()
