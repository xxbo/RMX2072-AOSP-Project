import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from usb_edl_return import parse_identity, QUERY


class EDLReturnTests(unittest.TestCase):
    sample = (b'RMX_EDL_BEGIN\r\n6.18.32-test\r\nedl-01\r\n 00 00 50 7f\r\n'
              b'configured\r\n25.40 160.00\r\n75\r\n\r\nRMX_EDL_END\r\n')

    def test_requires_live_response(self):
        self.assertEqual(parse_identity(QUERY + self.sample)['timer_seconds'], 75)
        for raw in (QUERY, self.sample.replace(b'50 7f', b'50 70'),
                    self.sample.replace(b'configured', b'not attached'),
                    self.sample.replace(b'6.18.', b'4.19.')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_identity(raw)
