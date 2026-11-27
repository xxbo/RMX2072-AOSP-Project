"""An interrupted native capture must not silently become GSI acceptance."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from compare_m3_stock_dsc import load_capture


class PausedCaptureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / 'trial'
        (self.record / 'live').mkdir(parents=True)
        self.manifest = Path(self.temp.name) / 'pause.json'
        self.boot = '790e9ef8-5e41-4066-8117-12222897de92'
        payload = '====================dsc_0================\n0x10 : 021c0000 02520200 00000020 00000007\n'
        self.files = {
            'inputs.json': '{}',
            'live/acm.log': 'captured before stopping',
            'live/host-events.jsonl': '\n'.join(json.dumps(dict(event=e, boot_id=self.boot))
                for e in ('handoff_requested', 'display_gate_requested')),
            'live/m3-display-at-pause.txt': (f'M3DISPLAY boot_id={self.boot}\n'
                'DRMSNAPSHOT begin=kms phase=after-flips\n' + payload +
                f'\nDRMSNAPSHOT end=kms bytes={len(payload)} limit_reached=0 read_errno=0\n'
                'DRMTEST exit=0\n'),
        }
        self.publish()

    def publish(self):
        evidence = {}
        for name, text in self.files.items():
            raw = text.encode()
            (self.record / name).write_bytes(raw)
            evidence[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.manifest.write_text(json.dumps(dict(status='PAUSED_BY_USER_F20_RESTORED',
            trial='trial', boot_id=self.boot, evidence=evidence)))

    def test_explicit_review_does_not_create_acceptance(self):
        result = load_capture(self.record, self.manifest)
        self.assertEqual(result['boot'], self.boot)
        self.assertIn('no GSI acceptance', result['identity_scope'])
        self.assertFalse((self.record / 'live/gsi-accepted.json').exists())
        with self.assertRaises(FileNotFoundError):
            load_capture(self.record)

    def test_modified_input_or_capture_rejected(self):
        for name in self.files:
            with self.subTest(name=name):
                self.publish()
                with (self.record / name).open('ab') as stream:
                    stream.write(b'changed')
                with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                    load_capture(self.record, self.manifest)

    def test_different_boot_rejected_even_with_matching_digests(self):
        for name in ('live/host-events.jsonl', 'live/m3-display-at-pause.txt'):
            with self.subTest(name=name):
                original = self.files[name]
                self.files[name] = original.replace(self.boot, 'another-boot')
                self.publish()
                with self.assertRaisesRegex(ValueError, 'boot mismatch'):
                    load_capture(self.record, self.manifest)
                self.files[name] = original

    def test_incomplete_probe_rejected(self):
        self.files['live/m3-display-at-pause.txt'] = self.files['live/m3-display-at-pause.txt'].replace(
            'DRMTEST exit=0', 'DRMTEST exit=1')
        self.publish()
        with self.assertRaisesRegex(ValueError, 'probe did not complete'):
            load_capture(self.record, self.manifest)


if __name__ == '__main__':
    unittest.main()
