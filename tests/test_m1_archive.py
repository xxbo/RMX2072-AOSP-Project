import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts/device_audit'
sys.path.insert(0, str(SCRIPTS))
from record_m1_vendor import recovery_events


class RecoveryTimelineTests(unittest.TestCase):
    def test_both_timelines_and_incomplete_or_misordered_events(self):
        path = SCRIPTS.parents[1]/'build/device/gsi17-project-vendor-2026-11-11.json'
        with tempfile.TemporaryDirectory() as tmp:
            events_file = Path(tmp)/'events.jsonl'
            for trial in json.loads(path.read_text())['trials']:
                rows = trial['recovery']['host_local_events']
                def replay(events):
                    events_file.write_text(''.join(json.dumps(row)+'\n' for row in events))
                    return recovery_events(events_file)
                with self.subTest(trial=trial['trial']):
                    self.assertEqual(rows, replay(rows))
                    with self.assertRaises(ValueError):
                        replay(rows[:-1])
                    with self.assertRaises(ValueError):
                        replay([dict(rows[0], at=rows[-1]['at']), *rows[1:]])
