"""Reject partial hardware evidence instead of silently decoding it as valid."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from decode_m3_kms_snapshot import extract, register_banks


class SnapshotEvidenceTest(unittest.TestCase):
    def test_exact_capture_and_independent_bank_offsets(self):
        payload = '====================dsc_0================\n0x10 : 021c0000 020e0200 00000020 00000007\n'
        text = ('DRMSNAPSHOT begin=kms phase=after-flips\n'+payload+
                f'\nDRMSNAPSHOT end=kms bytes={len(payload)} limit_reached=0 read_errno=0\n')
        self.assertEqual(extract(text, 'kms'), payload)
        self.assertEqual(register_banks(payload)['dsc_0'],
                         {16: 0x21c0000, 20: 0x20e0200, 24: 32, 28: 7})
        for invalid in (text.replace('limit_reached=0', 'limit_reached=1'),
                        text.replace('read_errno=0', 'read_errno=5'),
                        text.replace(f'bytes={len(payload)}', 'bytes=1'),
                        text.split('DRMSNAPSHOT end=')[0], text+text):
            with self.assertRaises(ValueError):
                extract(invalid, 'kms')

    def test_duplicate_register_rejected(self):
        with self.assertRaises(ValueError):
            register_banks('====dsc_0====\n'+
                           '0x0 : 00000005 003880ca 04380960 021c0030\n'*2)


if __name__ == '__main__':
    unittest.main()
