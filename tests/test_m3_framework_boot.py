"""Protect test-volume startup and accepted display settings during vendor work."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/build'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from pack_m2_source_boot import scratch_boot_argument
from rebuild_m3_graphics_trial import retained_display_flags


class FrameworkBootTests(unittest.TestCase):
    def test_only_verified_isolated_volumes_enable_startup(self):
        p = dict(autonomous_ufs=True, guarded_adb=True, scratch_volumes={
            name: dict(bytes=mib*1024**2, sha256='1'*64, gzip_sha256='2'*64)
            for name, mib in [('data', 512), ('metadata', 32)]})
        self.assertEqual(scratch_boot_argument(p), ' androidboot.rmx_scratch=1')
        larger = deepcopy(p)
        larger['scratch_volumes']['data']['bytes'] = 2048 << 20
        self.assertEqual(scratch_boot_argument(larger), ' androidboot.rmx_scratch=1')
        self.assertEqual(scratch_boot_argument({}), '')
        for change in [lambda x:x.update(guarded_adb=False),
                       lambda x:x['scratch_volumes'].pop('metadata'),
                       lambda x:x['scratch_volumes']['data'].update(bytes=8 << 30),
                       lambda x:x['scratch_volumes']['data'].update(sha256='')]:
            invalid = deepcopy(p)
            change(invalid)
            with self.assertRaises(ValueError):
                scratch_boot_argument(invalid)

    def test_vendor_rebuild_retains_trial69_display_fix(self):
        prior = dict(display_staged=True, single_dsc_test=True,
                     stock_linkclock_test=True, stock_dsc_test=True,
                     stock_phy_test=True, first_frame_trace=True,
                     panel_readback_test=True, standard_pps_test=True,
                     solid_fill_test=False)
        flags = retained_display_flags(prior, True)
        self.assertEqual(set(flags), {'--single-dsc-test', '--stock-linkclock-test',
            '--stock-dsc-test', '--stock-phy-test', '--first-frame-trace',
            '--panel-readback-test', '--standard-pps-test'})
        with self.assertRaises(ValueError):
            retained_display_flags(prior, False)
        prior['standard_pps_test'] = 'false'
        with self.assertRaises(ValueError):
            retained_display_flags(prior, True)


if __name__ == '__main__':
    unittest.main()
