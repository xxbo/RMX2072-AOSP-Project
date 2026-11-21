"""Decode bounded first-frame trace; missing evidence never means no error."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from compare_m3_stock_dsc import load_capture

# ACK cfa72fb3, registers/display/dsi.xml (blob c7a7b633).
# EMPTY, FULL and watermarks are intentionally not classified as errors.
FIFO_ERRORS = {0: 'VIDEO_OVERFLOW', 3: 'VIDEO_UNDERFLOW', 7: 'CMD_MDP_UNDERFLOW',
               10: 'CMD_DMA_UNDERFLOW', 14: 'DLN0_LP_OVERFLOW'}
for lane in range(4):
    FIFO_ERRORS[18 + 4 * lane] = f'DLN{lane}_HS_OVERFLOW'
    FIFO_ERRORS[19 + 4 * lane] = f'DLN{lane}_HS_UNDERFLOW'
FIELDS = ('irq', 'status', 'fifo', 'ack', 'timeout', 'phy', 'clk', 'mask')
PHASES = {0: 'power-ready', 1: 'kickoff-ready', 2: 'pp-done-handler',
          3: 'irq-preclear', 4: 'host-enable', 5: 'dpu-underrun-handler'}
EVENT = re.compile(r'(?P<time>\d+\.\d+): (?P<kind>rmx_dsi_sample|rmx_display_step): (?P<data>.*)$')
SAMPLE = re.compile(r'phase=(\d+) id=(\d+) cookie=(\d+) ' +
                    ' '.join(f'{field}=(0x[0-9a-f]+|0)' for field in FIELDS))
STEP = re.compile(r'step=([\w-]+) id=(\d+) a=(\d+) b=(\d+) c=(\d+) d=(\d+)')


def decode(snapshot, boot):
    problems = []
    def check(ok, message):
        if not ok:
            problems.append(message)
    # Parent and final display snapshot both print the same boot marker.
    boots = re.findall(r'^M3DISPLAY boot_id=(\S+)$', snapshot, re.M)
    check(bool(boots) and set(boots) == {boot}, 'display boot mismatch')
    check(re.findall(r'^M3FF armed=1 boot=(\S+) buffer_kb_per_cpu=256 overwrite=0 clock=mono$', snapshot, re.M) == [boot], 'missing or wrong trace arming')
    check(re.findall(r'^M3FF complete boot=(\S+)$', snapshot, re.M) == [boot], 'missing or wrong completion')
    blocks = re.findall(r'^M3CLKTRACE begin\n(.*?)^M3CLKTRACE end$', snapshot, re.M | re.S)
    check(len(blocks) == 1, 'trace block count differs from one')
    if len(blocks) != 1:
        return dict(complete=False, problems=problems, root_cause='NOT_ESTABLISHED')
    block = blocks[0]
    header = re.findall(r'^# entries-in-buffer/entries-written:\s*(\d+)/(\d+)\s+#P:(\d+)', block, re.M)
    check(len(header) == 1 and header[0][0] == header[0][1] and header[0][2] == '8', 'missing header or lost trace records')
    # This profile enables only single-line clock/custom events, no stacks.
    # Validate the exported text too, not merely the kernel's loss counters.
    lines = [line for line in block.split('M3FF stats=', 1)[0].splitlines()
             if line.strip() and not line.startswith('#')]
    check(all(re.search(r'\d+\.\d+: \w+: ', line) for line in lines), 'unexpected or truncated trace text')
    check(len(header) == 1 and len(lines) == int(header[0][0]), 'exported event count differs from buffer header')
    stats = {}
    for cpu, data in re.findall(r'^M3FF stats=\S+/cpu(\d+)/stats\n(.*?)(?=^M3FF |\Z)', block, re.M | re.S):
        check(int(cpu) not in stats, 'duplicate CPU statistics')
        values = {name: int(value) for name, value in re.findall(
            r'^(overrun|commit overrun|dropped events):\s*(\d+)\s*$', data, re.M)}
        stats[int(cpu)] = values
        check(set(values) == {'overrun', 'commit overrun', 'dropped events'}, 'missing loss counters')
        check(not any(values.values()), 'nonzero loss counters')
    check(set(stats) == set(range(8)), 'missing CPU statistics')

    events, samples, steps = [], [], []
    for line in block.splitlines():
        m = EVENT.search(line)
        if not m:
            check('rmx_dsi_sample:' not in line and 'rmx_display_step:' not in line, 'malformed event prefix')
            continue
        match = (SAMPLE if m['kind'] == 'rmx_dsi_sample' else STEP).fullmatch(m['data'])
        check(match is not None, 'malformed event payload')
        if not match:
            continue
        seconds, fraction = m['time'].split('.')
        row = dict(time_ns=int(seconds) * 10**9 + int(fraction.ljust(9, '0')),
                   kind=m['kind'])
        if m['kind'] == 'rmx_dsi_sample':
            phase, host, cookie, *raw = match.groups()
            row.update(phase=int(phase), id=int(host), cookie=int(cookie),
                       **dict(zip(FIELDS, (int(x, 0) for x in raw))))
            check(row['phase'] in PHASES and row['id'] == 0, 'unexpected sample host or phase')
            row['errors'] = [name for bit, name in FIFO_ERRORS.items() if row['fifo'] & (1 << bit)]
            if row['status'] & (1 << 31): row['errors'].append('INTERLEAVE_CONTENTION')
            if row['clk'] & (1 << 16): row['errors'].append('PLL_UNLOCKED')
            if row['ack']: row['errors'].append('ACK_NONZERO')
            if row['timeout']: row['errors'].append('TIMEOUT_NONZERO')
            if row['phy'] & 0x11111: row['errors'].append('DLN0_PHY_ERROR')
            if row['phase'] == 5: row['errors'].append('DPU_UNDERRUN_HANDLER')
            samples.append(row)
        else:
            step, host, *values = match.groups()
            row.update(step=step, id=int(host), **dict(zip('abcd', map(int, values))))
            steps.append(row)
        events.append(row)
    check(all(a['time_ns'] <= b['time_ns'] for a, b in zip(events, events[1:])), 'event time went backwards')
    phases = Counter(s['phase'] for s in samples)
    check(all(phases[p] for p in (0, 1, 2, 4)), 'missing initial power/enable/kickoff/completion samples')
    if all(phases[p] for p in (0, 1, 2, 4)):
        first = {p: next(s['time_ns'] for s in samples if s['phase'] == p) for p in (0, 1, 2, 4)}
        check(first[0] <= first[1] <= first[2] and first[4] <= first[2],
              'first active kickoff/completion ordering is incomplete')
    check(all(n <= 16 for n in phases.values()), 'sample limit exceeded')
    names = Counter(s['step'] for s in steps)
    check(all(names[n] for n in ('link-request', 'link-result', 'pll-prepare', 'pll-prepare-result', 'mdp-request', 'mdp-result', 'dcs-begin', 'dcs-end')), 'missing clock or command coverage')
    check('M3CLKTRACE setup_failed' not in snapshot and 'M3CLKTRACE capture_failed' not in snapshot, 'trace setup/capture failure')

    # Host command mutex serializes begin/restore; trace only reports restore,
    # not a successful DCS return value or the panel decoder's state.
    active, transactions, pll_during_command = {}, [], []
    for row in steps:
        host = row['id']
        if row['step'] == 'dcs-begin':
            check(host not in active, 'nested DCS capture')
            active[host] = row
        elif row['step'] == 'dcs-end':
            start = active.pop(host, None)
            check(start is not None and start['a'] == row['a'], 'unpaired DCS capture')
            if start:
                transactions.append(dict(id=host, seq=start['a'], type=start['b'] >> 32,
                    opcode=start['b'] & 0xffffffff, begin_ns=start['time_ns'], end_ns=row['time_ns']))
        elif row['step'] in ('pll-set-begin', 'pll-prepare', 'pll-unprepare') and host in active:
            pll_during_command.append(dict(event=row, command_seq=active[host]['a'],
                command_type=active[host]['b'] >> 32, opcode=active[host]['b'] & 0xffffffff))
    check(not active, 'unfinished DCS capture')
    return dict(complete=not problems, problems=problems, boot_id=boot,
        phase_counts=dict(phases), step_counts=dict(names), loss_counters=stats,
        saturated_phases=[PHASES[p] for p, n in phases.items() if n == 16],
        samples=samples, errors=[s for s in samples if s['errors']],
        steps=steps, transactions=transactions, pll_during_command=pll_during_command,
        pll_set_while_on=[s for s in steps if s['step'] == 'pll-set-begin' and s['d']],
        root_cause='NOT_ESTABLISHED', scope='Bounded native first-frame samples only; no physical acceptance or Android trace; saturated phases do not cover later events.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    capture = load_capture(a.record)
    inputs = json.loads((a.record / 'inputs.json').read_text(encoding='utf-8'))
    if not inputs['boot'].get('first_frame_trace') or not inputs['ramdisk'].get('first_frame_trace'):
        raise ValueError('Record is not an explicitly enabled first-frame candidate')
    result = decode(capture['snapshot'], capture['boot'])
    result.update(trial=inputs['trial'], kernel=inputs['kernel']['image_sha256'],
        snapshot_sha256=hashlib.sha256(capture['raw']).hexdigest())
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result.get(key) for key in ('complete', 'problems', 'phase_counts', 'step_counts', 'errors', 'pll_set_while_on')}))
    if not result['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
