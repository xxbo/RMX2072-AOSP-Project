"""Run the actual parent cleanup block with failed/timed-out probe fixtures."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

BASH = os.environ.get('RMX_TEST_BASH') or (shutil.which('bash') if os.name != 'nt' else None)
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(BASH, 'Set RMX_TEST_BASH to a POSIX bash executable')
class SolidCleanupTest(unittest.TestCase):
    def run_parent(self, probe, broken_control=False):
        source = (ROOT/'scripts/device_audit/first_stage_mount.sh').read_text()
        block = source.split('    probe_timeout=50\n', 1)[1].split(
            '    if [ -f /m3-display-staged ]; then', 1)[0]
        block = 'probe_timeout=1\n'+block.replace('probe_timeout=65', 'probe_timeout=1')
        with tempfile.TemporaryDirectory(prefix='rmx-solid-') as directory:
            temp = Path(directory)
            control, log, marker = (temp/n for n in ('control', 'display.log', 'marker'))
            marker.touch()
            if broken_control:
                control.mkdir()
            else:
                control.write_text('0\n')
            q = lambda p: shlex.quote(p.as_posix())
            child = temp/'probe.sh'
            child.write_text(('' if broken_control else "printf '2147483903\\n' > "+q(control)+'\n')+probe+'\n')
            block = block.replace('/m3-solid-fill-test', q(marker)).replace(
                '/sys/module/msm/parameters/rmx2072_solid_fill', q(control)).replace(
                '/run/m3-display.txt', q(log)).replace('/bin/drm-panel-smoke', 'bash '+q(child))
            parent = temp/'parent.sh'
            parent.write_text('set -eu\n'+block)
            result = subprocess.run([BASH, parent.as_posix()], capture_output=True, timeout=12)
            return result.returncode, log.read_text(), None if broken_control else control.read_text()

    def test_success_still_clears_a_probe_that_left_fill_enabled(self):
        code, log, control = self.run_parent('exit 0')
        self.assertEqual((code, control), (0, '0\n'))
        self.assertIn('M3SOLID parent_cleanup=ok parameter=0', log)

    def test_failed_probe_does_not_skip_cleanup_under_errexit(self):
        code, log, control = self.run_parent('exit 7')
        self.assertEqual((code, control), (0, '0\n'))
        self.assertIn('M3DISPLAY smoke_rc=7', log)

    def test_timeout_does_not_skip_cleanup(self):
        code, log, control = self.run_parent('sleep 5')
        self.assertEqual((code, control), (0, '0\n'))
        self.assertIn('M3DISPLAY smoke_rc=124', log)

    def test_failed_reset_blocks_handoff(self):
        code, log, _ = self.run_parent('exit 0', broken_control=True)
        self.assertEqual(code, 1)
        self.assertIn('M3SOLID parent_cleanup=FAILED', log)


if __name__ == '__main__':
    unittest.main()
