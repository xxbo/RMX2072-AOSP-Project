"""A host-gated diagnostic must not be reported as an autonomous handset boot."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from gsi_adb_accept import fetch_autonomous


class DisplayGateTest(unittest.TestCase):
    boot = '83f1a4a6-3a5c-4a21-a23d-13cfe503675f'

    def evidence(self, autonomous):
        return f'M1EVENT autonomous={autonomous}\nM1EVENT boot_id={self.boot}\n' + (
            'M1EVENT display_staged=1\n' if not autonomous else '')

    def run_capture(self, directory, evidence):
        with patch('gsi_adb_accept.shell', side_effect=[self.boot, evidence]):
            return fetch_autonomous(directory)

    def test_matching_gate_is_explicitly_non_autonomous(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/'host-events.jsonl').write_text(json.dumps(dict(event='display_gate_requested', boot_id=self.boot))+'\n')
            self.assertEqual(self.run_capture(d, self.evidence(0)), self.boot)
            events = [json.loads(x) for x in (d/'host-events.jsonl').read_text().splitlines()]
            self.assertEqual(events[-1]['event'], 'staged_display_handoff_observed')
            self.assertNotIn('autonomous_handoff_observed', [x['event'] for x in events])

    def test_other_boot_gate_cannot_accept_staged_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d/'host-events.jsonl').write_text(json.dumps(dict(event='display_gate_requested', boot_id='different'))+'\n')
            with self.assertRaisesRegex(ValueError, 'matching USB host gate'):
                self.run_capture(d, self.evidence(0))
            self.assertFalse((d/'boot-events.txt').exists())

    def test_existing_autonomous_boot_needs_no_host_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(self.run_capture(d, self.evidence(1)), self.boot)
            self.assertEqual(json.loads((d/'host-events.jsonl').read_text())['event'], 'autonomous_handoff_observed')


if __name__ == '__main__':
    unittest.main()
