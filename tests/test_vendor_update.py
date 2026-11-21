"""Bound a retained-GSI vendor update and include chunks reverting to stock."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from run_ufs_trial import validate_vendor_update


class VendorUpdateTests(unittest.TestCase):
    def setUp(self):
        old = dict(source_sha256='f'*64, bytes=8866758656,
                   signed=dict(system={'sha256':'1'*64}, vendor={'key_sha256':'2'*64, 'bytes':17 << 20}),
                   partitions_after=[{'system':'1'*64, 'vendor':'3'*64, 'odm':'4'*64}],
                   parts=[format(n, '064x') for n in range(17)])
        self.previous = dict(candidate=old, scratch={'seed':'5'*64}, boot={'boot_sha256':'6'*64})
        self.candidate = deepcopy(old)
        self.candidate['signed']['vendor']['bytes'] = 100 << 20
        self.candidate['partitions_after'][0]['vendor'] = '7'*64
        self.candidate['parts'][1] = '8'*64
        self.stable = {'identity':['37','kernel','9d9585b2-a24a-4117-8390-fb2a29e471a1','Enforcing','running','','retained','adb'],
                       'guardian':'retained', 'seconds':193}

    def check(self):
        return validate_vendor_update(self.previous, self.stable, self.candidate,
                                      self.previous['scratch'], self.stable)

    def test_changed_vendor_is_allowed(self):
        self.assertEqual(self.check(), ('6'*64, [1]))

    def test_reversion_to_stock_bytes_is_still_written(self):
        self.previous['candidate']['parts'][0] = 'a'*64
        self.assertEqual(self.check()[1], [0, 1])

    def test_gsi_key_and_nonvendor_partitions_are_fixed(self):
        for mutate in [lambda c:c['signed']['system'].update(sha256='b'*64),
                       lambda c:c['signed']['vendor'].update(key_sha256='b'*64),
                       lambda c:c['partitions_after'][0].update(odm='b'*64)]:
            saved = deepcopy(self.candidate)
            mutate(self.candidate)
            with self.assertRaises(ValueError):
                self.check()
            self.candidate = saved

    def test_incomplete_physical_manifest_is_rejected(self):
        self.previous['candidate']['parts'].pop()
        with self.assertRaisesRegex(ValueError, '17-chunk'):
            self.check()


if __name__ == '__main__':
    unittest.main()
