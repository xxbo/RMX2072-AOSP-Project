"""Regression: firmware payload preparation must not rewrite ZIP/PNG bytes."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/build'))
from build_m1_vendor import source_bytes


class VendorBinaryPayloadTest(unittest.TestCase):
    def test_stored_archive_retains_crc_and_embedded_crlf(self):
        content = b'\x89PNG\r\n\x1a\nopaque payload\r\n'
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr('part0/00000.png', content)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bootanimation.zip'
            path.write_bytes(raw.getvalue())
            prepared = source_bytes(path)
        self.assertEqual(prepared, raw.getvalue())
        with zipfile.ZipFile(io.BytesIO(prepared)) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('part0/00000.png'), content)

    def test_unknown_binary_and_existing_text_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'vendor.avbpubkey'
            binary.write_bytes(b'\x00\xff\r\n\x80')
            self.assertEqual(source_bytes(binary), binary.read_bytes())
            text = root / 'init.qcom.rc'
            text.write_bytes(b'on boot\r\n    setprop test 1\r\n')
            self.assertEqual(source_bytes(text), b'on boot\n    setprop test 1\n')


if __name__ == '__main__':
    unittest.main()
