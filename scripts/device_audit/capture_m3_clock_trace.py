"""Bounded CPU/devfreq trace on an accepted GSI; restore tracing controls."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=60)
    p.add_argument('--phase', choices=('baseline', 'interaction', 'idle'), default='interaction')
    a = p.parse_args()
    if not 1 <= a.seconds <= 120:
        p.error('Capture 1..120 seconds')
    live = a.record.resolve()/'live'
    boot = json.loads((live/'gsi-accepted.json').read_text())['identity'][2]
    out = live/('clock-trace-'+a.phase)
    out.mkdir(exist_ok=False)
    base = '/sys/kernel/tracing/'

    def shell(command, timeout=15):
        return subprocess.check_output(['adb', '-s', 'RMX2072-M1', 'shell', command],
            timeout=timeout, stderr=subprocess.STDOUT).decode('utf-8', errors='replace').replace('\r', '')

    def identity():
        if shell('cat /proc/sys/kernel/random/boot_id').strip() != boot:
            raise ValueError('Accepted GSI boot changed')

    def put(path, value):
        if not value.isdigit():
            raise ValueError('Only numeric tracing controls may be written')
        shell('echo '+value+' > '+base+path)
        if shell('cat '+base+path).strip() != value:
            raise ValueError('Tracing control readback mismatch: '+path)

    identity()
    paths = ['tracing_on', 'events/power/cpu_frequency/enable',
             'events/devfreq/devfreq_frequency/enable']
    before = {n: shell('cat '+base+n).strip() for n in paths}
    if before['tracing_on'] != '0' or any(not v.isdigit() for v in before.values()):
        raise ValueError('Requires idle tracing with numeric controls')
    (out/'before.json').write_text(json.dumps(dict(boot_id=boot, controls=before,
        clock=shell('cat '+base+'trace_clock').strip(),
        buffer_size=shell('cat '+base+'buffer_size_kb').strip()), indent=2)+'\n')
    (out/'previous-trace.txt').write_text(shell('cat '+base+'trace', 30), encoding='utf-8')
    changed = []
    try:
        for n, value in [('events/power/cpu_frequency/enable', '1'),
                         ('events/devfreq/devfreq_frequency/enable', '1')]:
            changed.append(n)
            put(n, value)
        shell('echo > '+base+'trace')
        changed.append('tracing_on')
        put('tracing_on', '1')
        print('CLOCK_TRACE_STARTED boot='+boot+' seconds='+str(a.seconds), flush=True)
        deadline = time.monotonic()+a.seconds
        while time.monotonic() < deadline:
            time.sleep(min(5, max(0, deadline-time.monotonic())))
            identity()
        put('tracing_on', '0')
        (out/'trace.txt').write_text(shell('cat '+base+'trace', 30), encoding='utf-8')
    finally:
        identity()
        errors = []
        for n in reversed(changed):
            try:
                put(n, before[n])
            except Exception as error:
                errors.append(str(error))
        after = {n: shell('cat '+base+n).strip() for n in paths}
        (out/'after.json').write_text(json.dumps(dict(controls=after, errors=errors,
            restored=after == before and not errors), indent=2)+'\n')
        if errors or after != before:
            raise RuntimeError('Trace control restoration failed: '+repr(errors))
    print('CLOCK_TRACE_COMPLETE controls_restored=true', flush=True)


if __name__ == '__main__':
    main()
