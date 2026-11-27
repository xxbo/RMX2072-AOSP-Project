"""A successful-looking return cannot replace a complete PPS witness."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from compare_m3_standard_pps import standard_packets


def fixture():
    return 'RMXPPS standard-transfer ret=132 payload=128\n' + ''.join(
        f'RMXPPS standard-tx offset={i} bytes={bytes(range(i,i+32)).hex()}\n' for i in range(0,128,32))


class StandardPpsTest(unittest.TestCase):
    def test_complete_dma_return(self):
        self.assertEqual(standard_packets(fixture())[0]['data'], bytes(range(128)))

    def test_missing_chunk_duplicate_and_short_return_rejected(self):
        data = fixture()
        variants = [data.rsplit('RMXPPS standard-tx', 1)[0], data.replace('offset=32', 'offset=0'),
                    data.replace('ret=132', 'ret=127'), data.replace('ret=132', 'ret=-5'),
                    data.replace('payload=128', 'payload=88'),
                    data + 'RMXPPS standard-transfer ret=TRUNCATED payload=128\n',
                    '\n'.join(data.splitlines()[1:])]
        for text in variants:
            with self.subTest(text=text[:50]), self.assertRaises(ValueError):
                standard_packets(text)


if __name__ == '__main__':
    unittest.main()
