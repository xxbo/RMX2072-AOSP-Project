import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from record_ufs_first_stage import adb_observations, full_read
from record_ufs_scratch import keymaster_observations


class UfsInitReadTest(unittest.TestCase):
    def test_keymaster_reply_requires_matching_init_service_and_client(self):
        console = """[ 8.0][ T1] init: ... started service 'vendor.rmx-keymaster' has pid 32
[ 9.0][ T32] ks_log: (uprobe) tag="RMXKeymaster" msg="registered default"
[ 9.1][ T32] ks_log: (uprobe) tag="RMXKeymaster" msg="getHardwareInfo caller=21 level=TEE name=test"
"""
        self.assertEqual(keymaster_observations('', console, 22), {})
        self.assertEqual(keymaster_observations('', console.replace('T32]', 'T31]'), 21), {})
        reply = keymaster_observations('', console, 21)['gsi_hidl_reply']
        self.assertEqual((reply['caller_pid'], reply['service_pid'], reply['name']), (21, 32, 'test'))

    def test_read_requires_pid_device_count_and_post_stage_timestamp(self):
        def row(when, pid=1, device=266338318, result=5675):
            return (f'[{when:12.6f}][   T{pid}] m1_file_read: (vfs_read) '
                    f'ino=659 dev={device} count=5675 result={result}')

        wrong = '\n'.join([row(37), row(42, pid=31), row(42, device=266338319), row(42, result=21)])
        with self.assertRaises(ValueError):
            full_read(wrong, 659, '254:14', 5675, 40)
        read = full_read(wrong + '\n' + row(43), 659, '254:14', 5675, 40)
        self.assertEqual((read['at_seconds'], read['returned_bytes']), (43, 5675))

    def test_vold_read_can_request_more_than_file_size(self):
        line = '[   40.600000][ T1777] m1_file_read: (vfs_read) ino=14 dev=266338319 count=4096 result=220'
        result = full_read(line, 14, '254:15', 220, 40, pid=1777)
        self.assertEqual(result['requested_bytes'], 4096)
        with self.assertRaises(ValueError):
            full_read(line, 14, '254:15', 220, 40, pid=1)

    def test_stock_adb_outside_handoff_does_not_qualify(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp)
            events = [dict(monotonic=10, boot_id='trial', event='handoff_requested'),
                      dict(monotonic=13, boot_id='next', event='recovery_boot')]
            rows = [dict(monotonic=9, transports=['stock device']),
                    dict(monotonic=11, transports=[], diagnostic_acm=True),
                    dict(monotonic=12, transports=[]), dict(monotonic=14, transports=['stock device'])]
            for name, entries in [('host-events.jsonl', events), ('adb.jsonl', rows)]:
                (capture/name).write_text('\n'.join(map(json.dumps, entries)))
            result = adb_observations(capture, dict(boot_id='trial', kernel='6.18'))
            self.assertEqual(result['result'], 'NO_TRANSPORT_OBSERVED')
            self.assertEqual(result['samples'], 2)
            self.assertTrue(result['diagnostic_acm_seen'])
