"""Bounded Vulkan transfer load with read-only devfreq sampling on retained GSI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    boot = json.loads((a.record / 'live/gsi-stable.json').read_text())['identity'][2]
    a.output.mkdir(parents=True, exist_ok=False)
    base = [a.adb, '-s', 'RMX2072-M1']

    def shell(command, timeout=20):
        r = subprocess.run(base + ['shell', command], capture_output=True, timeout=timeout)
        text = r.stdout.decode('utf-8', 'replace').replace('\r', '')
        if r.returncode:
            raise RuntimeError(text + r.stderr.decode('utf-8', 'replace'))
        return text

    def identity():
        actual = shell('cat /proc/sys/kernel/random/boot_id; getenforce; '
                       'getprop vendor.rmx.m1.state; getprop sys.boot_completed').splitlines()
        if actual != [boot, 'Enforcing', 'retained', '1']:
            raise RuntimeError('Unexpected boot/guard state: ' + repr(actual))

    gpu = '/sys/class/devfreq/3d00000.gpu'
    config = 'cat ' + ' '.join(gpu + '/' + f for f in
                              ('governor', 'min_freq', 'max_freq', 'polling_interval'))
    identity()
    before = shell(config)
    (a.output / 'controls-before.txt').write_text(before, encoding='utf-8')
    (a.output / 'transitions-before.txt').write_text(shell('cat ' + gpu + '/trans_stat'), encoding='utf-8')
    (a.output / 'thermal-before.txt').write_text(shell('dumpsys battery; for p in /sys/class/thermal/thermal_zone*; do cat "$p/type" "$p/temp"; done; true'), encoding='utf-8')
    remote = '/data/local/tmp/rmx-gpu-dvfs-probe'
    subprocess.run(base + ['push', str(a.probe), remote], check=True, capture_output=True)
    process = None
    samples = []
    try:
        shell('chmod 700 ' + remote)
        smoke = shell('timeout 12 ' + remote)
        (a.output / 'smoke.txt').write_text(smoke, encoding='utf-8')
        if 'VKTEST PASS' not in smoke:
            raise RuntimeError('Hardware submission prerequisite failed')

        def sample(phase, seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                hz = int(shell('cat ' + gpu + '/cur_freq').strip())
                samples.append(dict(monotonic=time.monotonic(), phase=phase, hz=hz))
                time.sleep(.1)

        sample('baseline', 3)
        process = subprocess.Popen(base + ['shell', 'timeout 16 ' + remote + ' --load-seconds 8'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        sample('load', 8)
        raw, _ = process.communicate(timeout=12)
        load = raw.decode('utf-8', 'replace').replace('\r', '')
        (a.output / 'load.txt').write_text(load, encoding='utf-8')
        if process.returncode or 'VKTEST PASS' not in load:
            raise RuntimeError('Bounded GPU load failed; see load.txt')
        sample('recovery', 10)
        identity()
        after = shell(config)
        (a.output / 'controls-after.txt').write_text(after, encoding='utf-8')
        if before != after:
            raise RuntimeError('GPU controls changed during capture')
        (a.output / 'transitions-after.txt').write_text(shell('cat ' + gpu + '/trans_stat'), encoding='utf-8')
        (a.output / 'thermal-after.txt').write_text(shell('dumpsys battery; for p in /sys/class/thermal/thermal_zone*; do cat "$p/type" "$p/temp"; done; true'), encoding='utf-8')
        summary = dict(boot_id=boot, same_boot=True, controls_unchanged=True,
                       probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest(),
                       scope='Vulkan transfer/fence/readback; devfreq-reported frequency, not sustained UI FPS',
                       phases={phase: sorted({s['hz'] for s in samples if s['phase'] == phase})
                               for phase in ('baseline', 'load', 'recovery')},
                       last_recovery_hz=samples[-1]['hz'])
        (a.output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary))
    finally:
        (a.output / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n', encoding='utf-8')
        if process is not None and process.poll() is None:
            # Device-side timeout bounds the load even if the host disconnects.
            process.terminate()
            process.wait(timeout=5)
        try:
            shell('rm -f ' + remote)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass


if __name__ == '__main__':
    main()
