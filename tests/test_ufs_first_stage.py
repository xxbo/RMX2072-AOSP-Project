from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/device_audit'))
from record_ufs_first_stage import full_read


class UfsInitReadTest(unittest.TestCase):
    def test_read_requires_pid_device_count_and_post_stage_timestamp(self):
        def row(when, pid=1, device=266338318, result=5675):
            return (f'[{when:12.6f}][   T{pid}] m1_file_read: (vfs_read) '
                    f'ino=659 dev={device} count=5675 result={result}')

        wrong = '\n'.join([row(37), row(42, pid=31), row(42, device=266338319), row(42, result=21)])
        with self.assertRaises(ValueError):
            full_read(wrong, 659, '254:14', 5675, 40)
        read = full_read(wrong + '\n' + row(43), 659, '254:14', 5675, 40)
        self.assertEqual((read['at_seconds'], read['returned_bytes']), (43, 5675))
