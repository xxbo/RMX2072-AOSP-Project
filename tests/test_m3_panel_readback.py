"""Reject logs that could turn truncated/unsupported reads into decoder evidence."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from decode_m3_panel_readback import transactions


def tx_log(data=bytes(range(88))):
    return 'RMXPPS host-transfer ret=96 payload=88\n'+''.join(
        f'RMXPPS tx offset={offset} bytes={data[offset:offset+32].hex()}\n'
        for offset in range(0,len(data),32))


class ReadbackEvidenceTest(unittest.TestCase):
    def test_unsupported_read_is_recorded_without_payload(self):
        tx, reads = transactions(tx_log()+'RMXPANEL read command=0a requested=1 ret=-110\n')
        self.assertEqual(len(tx[0]['data']),88)
        self.assertEqual(reads[0]['returned'],-110)
        self.assertEqual(reads[0]['data'],b'')

    def test_old_64_byte_truncation_is_rejected(self):
        with self.assertRaises(ValueError):
            transactions(tx_log(bytes(range(64)))+'RMXPANEL read command=0a requested=1 ret=-110\n')

    def test_duplicate_chunk_is_rejected(self):
        with self.assertRaises(ValueError):
            transactions(tx_log()+'RMXPPS tx offset=64 bytes='+bytes(range(64,88)).hex()+'\n')

    def test_response_length_claim_without_bytes_is_rejected(self):
        with self.assertRaises(ValueError):
            transactions(tx_log()+'RMXPANEL read command=9e requested=88 ret=88\n')

    def test_two_transmits_are_kept_separate(self):
        tx, reads = transactions(tx_log()+tx_log()+
            'RMXPANEL read command=0a requested=1 ret=1\nRMXPPS power offset=0 bytes=9c\n')
        self.assertEqual(len(tx),2)
        self.assertEqual(reads[0]['data'],b'\x9c')


if __name__ == '__main__':
    unittest.main()
