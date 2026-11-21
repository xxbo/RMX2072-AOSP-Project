"""Reject the stale completion events physically observed in trial 42."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from record_m3_display import evaluate_kms


class KmsEvidenceTest(unittest.TestCase):
    def record(self, advancing):
        return '\n'.join(f'DRMTEST flip={n} sequence={40+n if advancing else 40} time={34+n if advancing else 34}.955539'
                         for n in range(1, 5))+'\nDRMTEST kms_scanout=PASS physical_observation=REQUIRED\n'

    def test_trial42_stale_events_are_not_a_pass(self):
        result = evaluate_kms(self.record(False))
        self.assertTrue(result['probe_reported_pass'])
        self.assertFalse(result['advancing_vblank_events'])
        self.assertEqual(result['drm_kms_result'], 'BLOCKED_OR_FAILED')

    def test_advancing_events_do_not_claim_physical_output(self):
        self.assertEqual(evaluate_kms(self.record(True))['drm_kms_result'], 'PASS_EVENTS_ONLY')

    def test_transport_error_rejects_otherwise_advancing_events(self):
        result = evaluate_kms(self.record(True)+'panel: packet 0 DCS=9f failed: -110\n')
        self.assertTrue(result['advancing_vblank_events'])
        self.assertEqual(result['drm_kms_result'], 'BLOCKED_OR_FAILED')

    def test_missing_device_is_not_a_pass(self):
        self.assertFalse(evaluate_kms('DRMTEST blocked=no-card0 errno=2\n')['probe_reported_pass'])


if __name__ == '__main__':
    unittest.main()
