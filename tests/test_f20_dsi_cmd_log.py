"""Reject truncated software packet witnesses before interpreting PPS."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from analyze_f20_dsi_cmd_log import packets


class PacketLogTest(unittest.TestCase):
    def test_length_and_type_are_independent_of_error_log_level(self):
        row = '[ 1.250000] [drm:dsi_message_tx] *ERROR* : dsi-ctrl-0: 0A 01 00 0A 00 00 02 11 00 '
        result = packets('\x1b[31m' + row + '\x1b[0m')[0]
        self.assertEqual(result['type'], 10)
        self.assertEqual(result['payload_hex'], '1100')
        self.assertNotIn('failed', result)

    def test_missing_extra_invalid_payload_is_rejected(self):
        head = '[ 1.250000] [drm:dsi_message_tx] *ERROR* : dsi-ctrl-0: '
        for value in ('0A 01 00 0A 00 00 80 11', '05 01 00 08 00 00 01 29 FF',
                      '05 01 00 08 00 00 01 XX', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                packets(head + value)


if __name__ == '__main__':
    unittest.main()
