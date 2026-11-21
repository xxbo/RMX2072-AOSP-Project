"""Protect negative conclusions from incomplete or ambiguous display traces."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/device_audit'))
from decode_m3_first_frame import decode

BOOT = '790e9ef8-5e41-4066-8117-12222897de92'


def fixture(fifo='0x11111000', pll=False):
    events = []
    def add(kind, data):
        events.append(f'worker-1 [000] .... 31.{len(events):06d}: {kind}: {data}')
    def step(name, a=0, b=0, c=0, d=0):
        add('rmx_display_step', f'step={name} id=0 a={a} b={b} c={c} d={d}')
    step('link-request', 82500000, 110000000)
    step('link-result', 82500000, 110000000)
    step('mdp-request', 200000000)
    step('mdp-result', 200000000, 200000000)
    step('pll-prepare', 660000000)
    step('pll-prepare-result', 660000000, 1)
    step('dcs-begin', 1, (0x39 << 32) | 0x51, 3, 1 << 32)
    if pll:
        step('pll-set-begin', 660000000, 19200000, 660000000, 1)
        step('pll-set-end', 660000000, 19200000, 660000000, 1)
    step('dcs-end', 1, 0x39, 3)
    for phase in (0, 4, 1, 2):
        add('rmx_dsi_sample', f'phase={phase} id=0 cookie=0 irq=0 status=0x7 fifo={fifo} ack=0 timeout=0 phy=0 clk=0x303f mask=0x13ff3be0')
    stats = ''.join(f'M3FF stats=/sys/kernel/debug/tracing/instances/rmx_m3_clk/per_cpu/cpu{i}/stats\n'
                    'entries: 10\noverrun: 0\ncommit overrun: 0\ndropped events: 0\n' for i in range(8))
    return (f'M3DISPLAY boot_id={BOOT}\n'
        f'M3FF armed=1 boot={BOOT} buffer_kb_per_cpu=256 overwrite=0 clock=mono\n'
        'M3CLKTRACE begin\n'
        f'# entries-in-buffer/entries-written: {len(events)}/{len(events)}   #P:8\n' +
        '\n'.join(events) + '\n' + stats + f'M3FF complete boot={BOOT}\nM3CLKTRACE end\n')


class FirstFrameTest(unittest.TestCase):
    def test_empty_fifos_busy_status_not_error_or_physical_pass(self):
        result = decode(fixture(), BOOT)
        self.assertTrue(result['complete'], result['problems'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['root_cause'], 'NOT_ESTABLISHED')

    def test_masked_underflow_is_retained(self):
        result = decode(fixture(fifo='0x11111080'), BOOT)
        self.assertTrue(result['complete'])
        self.assertIn('CMD_MDP_UNDERFLOW', result['errors'][0]['errors'])
        self.assertTrue(result['errors'][0]['mask'] & (1 << 11))

    def test_loss_or_partial_trace_cannot_support_absence(self):
        text = fixture()
        variants = [text.replace('overrun: 0', 'overrun: 1', 1),
                    text.replace('dropped events: 0', 'dropped events: 1', 1),
                    text.replace('commit overrun: 0', 'commit overrun: 1', 1),
                    text.replace(f'M3FF complete boot={BOOT}', ''),
                    text.replace('phase=2', 'phase=1'),
                    text.replace('/cpu7/stats', '/cpu6/stats'),
                    text.replace('timeout=0', 'timeout=TRUNCATED', 1),
                    '\n'.join(line for line in text.splitlines() if 'step=link-result' not in line),
                    text.replace('#P:8', '#P:4')]
        for changed in variants:
            with self.subTest(change=changed[-200:]):
                self.assertFalse(decode(changed, BOOT)['complete'])

    def test_boot_identity_must_match_all_markers(self):
        self.assertFalse(decode(fixture(), 'another-boot')['complete'])
        text = fixture().replace(f'M3FF complete boot={BOOT}', 'M3FF complete boot=another')
        self.assertFalse(decode(text, BOOT)['complete'])

    def test_parent_and_final_snapshot_may_repeat_same_boot_marker(self):
        self.assertTrue(decode(fixture()+f'M3DISPLAY boot_id={BOOT}\n', BOOT)['complete'])
        self.assertFalse(decode(fixture()+'M3DISPLAY boot_id=another\n', BOOT)['complete'])

    def test_actual_pll_programming_is_distinct_from_link_request(self):
        baseline = decode(fixture(), BOOT)
        changed = decode(fixture(pll=True), BOOT)
        self.assertEqual(baseline['pll_set_while_on'], [])
        self.assertEqual(len(changed['pll_set_while_on']), 1)
        self.assertEqual(changed['pll_during_command'][0]['opcode'], 0x51)
        self.assertEqual(changed['root_cause'], 'NOT_ESTABLISHED')

    def test_unpaired_commands_rejected(self):
        text = fixture().replace('step=dcs-end id=0 a=1', 'step=dcs-end id=0 a=2')
        self.assertFalse(decode(text, BOOT)['complete'])

    def test_missing_first_kickoff_not_replaced_by_later_flip(self):
        text = fixture().replace('phase=1', 'phase=TEMP').replace('phase=2', 'phase=1').replace('phase=TEMP', 'phase=2')
        self.assertFalse(decode(text, BOOT)['complete'])


if __name__ == '__main__':
    unittest.main()
